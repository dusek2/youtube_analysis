import os
import csv
from datetime import datetime, timezone
from dateutil import parser as date_parser
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound


API_KEY = os.environ.get('YOUTUBE_API_KEY')


def get_service():
    if not API_KEY:
        raise ValueError('YOUTUBE_API_KEY environment variable not set')
    return build('youtube', 'v3', developerKey=API_KEY)


def search_channel_id(youtube, handle):
    handle = handle.lstrip('@')
    request = youtube.search().list(part='snippet', q=handle, type='channel', maxResults=1)
    response = request.execute()
    items = response.get('items', [])
    if not items:
        raise ValueError(f'Channel with handle {handle} not found')
    return items[0]['snippet']['channelId']


def get_uploads_playlist_id(youtube, channel_id):
    request = youtube.channels().list(part='contentDetails', id=channel_id)
    response = request.execute()
    items = response.get('items', [])
    if not items:
        raise ValueError(f'Channel {channel_id} not found')
    return items[0]['contentDetails']['relatedPlaylists']['uploads']


def list_videos(youtube, playlist_id, start_date, end_date):
    videos = []
    next_page = None
    while True:
        request = youtube.playlistItems().list(part='contentDetails', playlistId=playlist_id, maxResults=50, pageToken=next_page)
        response = request.execute()
        for item in response.get('items', []):
            video_id = item['contentDetails']['videoId']
            published_at = item['contentDetails']['videoPublishedAt']
            published = date_parser.isoparse(published_at)
            if start_date <= published <= end_date:
                videos.append((video_id, published))
        next_page = response.get('nextPageToken')
        if not next_page:
            break
    return videos


def get_video_details(youtube, video_ids):
    request = youtube.videos().list(part='snippet,statistics', id=','.join(video_ids))
    response = request.execute()
    details = {}
    for item in response.get('items', []):
        vid = item['id']
        snippet = item['snippet']
        stats = item.get('statistics', {})
        details[vid] = {
            'title': snippet['title'],
            'description': snippet.get('description', ''),
            'publishedAt': snippet['publishedAt'],
            'viewCount': stats.get('viewCount', '0'),
            'likeCount': stats.get('likeCount', '0'),
            'commentCount': stats.get('commentCount', '0')
        }
    return details


def fetch_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        text = '\n'.join([entry['text'] for entry in transcript])
        return text
    except (TranscriptsDisabled, NoTranscriptFound):
        return ''


def save_output(videos, output_dir='output'):
    os.makedirs(output_dir, exist_ok=True)
    transcripts_dir = os.path.join(output_dir, 'transcripts')
    os.makedirs(transcripts_dir, exist_ok=True)
    csv_path = os.path.join(output_dir, 'videos.csv')
    fieldnames = ['video_id', 'publishedAt', 'title', 'description', 'viewCount', 'likeCount', 'commentCount', 'transcript_path']
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for video in videos:
            transcript_file = os.path.join('transcripts', f"{video['video_id']}.txt")
            full_path = os.path.join(output_dir, transcript_file)
            if video['transcript']:
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(video['transcript'])
            writer.writerow({k: video.get(k, '') for k in fieldnames})


def main(channel_handle, start_date, end_date):
    start_dt = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    youtube = get_service()
    channel_id = search_channel_id(youtube, channel_handle)
    playlist_id = get_uploads_playlist_id(youtube, channel_id)
    vids = list_videos(youtube, playlist_id, start_dt, end_dt)
    all_videos = []
    for i in range(0, len(vids), 50):
        batch_ids = [vid for vid, _ in vids[i:i+50]]
        details = get_video_details(youtube, batch_ids)
        for vid, published in vids[i:i+50]:
            info = details.get(vid, {})
            transcript = fetch_transcript(vid)
            all_videos.append({
                'video_id': vid,
                'publishedAt': info.get('publishedAt'),
                'title': info.get('title'),
                'description': info.get('description'),
                'viewCount': info.get('viewCount'),
                'likeCount': info.get('likeCount'),
                'commentCount': info.get('commentCount'),
                'transcript_path': os.path.join('transcripts', f"{vid}.txt"),
                'transcript': transcript
            })
    save_output(all_videos)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Fetch YouTube channel data and transcripts')
    parser.add_argument('--handle', required=True, help='Channel handle (e.g., @KamFIT24) or name')
    parser.add_argument('--start', required=True, help='Start date YYYY-MM-DD')
    parser.add_argument('--end', required=True, help='End date YYYY-MM-DD')
    args = parser.parse_args()
    main(args.handle, args.start, args.end)
