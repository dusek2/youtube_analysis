import os
import csv
import logging
from datetime import datetime, timezone
from dateutil import parser as date_parser
from googleapiclient.discovery import build

from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


API_KEY = os.environ.get('YOUTUBE_API_KEY')


def get_service():
    if not API_KEY:
        raise ValueError('YOUTUBE_API_KEY environment variable not set')
    logger.info('Initializing YouTube service')
    return build('youtube', 'v3', developerKey=API_KEY)


def search_channel_id(youtube, handle):
    handle = handle.lstrip('@')
    logger.info('Searching for channel ID for handle %s', handle)
    request = youtube.search().list(part='snippet', q=handle, type='channel', maxResults=1)
    response = request.execute()
    items = response.get('items', [])
    if not items:
        raise ValueError(f'Channel with handle {handle} not found')
    channel_id = items[0]['snippet']['channelId']
    logger.info('Found channel ID %s', channel_id)
    return channel_id


def get_uploads_playlist_id(youtube, channel_id):
    logger.info('Retrieving uploads playlist for channel %s', channel_id)
    request = youtube.channels().list(part='contentDetails', id=channel_id)
    response = request.execute()
    items = response.get('items', [])
    if not items:
        raise ValueError(f'Channel {channel_id} not found')
    playlist_id = items[0]['contentDetails']['relatedPlaylists']['uploads']
    logger.info('Uploads playlist ID is %s', playlist_id)
    return playlist_id


def list_videos(youtube, playlist_id, start_date, end_date):
    logger.info(
        'Listing videos in playlist %s between %s and %s',
        playlist_id,
        start_date.date(),
        end_date.date(),
    )
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
    logger.info('Found %d videos', len(videos))
    return videos


def get_video_details(youtube, video_ids):
    logger.info('Fetching details for %d videos', len(video_ids))
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
    logger.info('Fetching transcript for video %s', video_id)
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        text = '\n'.join([entry['text'] for entry in transcript])
        return text
    except (TranscriptsDisabled, NoTranscriptFound):
        logger.info('Transcript not available for video %s', video_id)
        return ''


def save_output(videos, output_dir='output'):
    logger.info('Saving output to %s', output_dir)
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
                logger.info('Wrote transcript for video %s', video['video_id'])
            writer.writerow({k: video.get(k, '') for k in fieldnames})


def main(channel_handle, start_date, end_date):
    logger.info('Starting fetch for channel %s', channel_handle)
    start_dt = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    youtube = get_service()
    channel_id = search_channel_id(youtube, channel_handle)
    playlist_id = get_uploads_playlist_id(youtube, channel_id)
    vids = list_videos(youtube, playlist_id, start_dt, end_dt)
    all_videos = []
    for i in range(0, len(vids), 50):
        batch_ids = [vid for vid, _ in vids[i:i+50]]
        logger.info('Processing videos %d to %d', i + 1, i + len(batch_ids))
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
    logger.info('Done')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Fetch YouTube channel data and transcripts')
    parser.add_argument('--handle', required=True, help='Channel handle (e.g., @KamFIT24) or name')
    parser.add_argument('--start', required=True, help='Start date YYYY-MM-DD')
    parser.add_argument('--end', required=True, help='End date YYYY-MM-DD')
    args = parser.parse_args()
    main(args.handle, args.start, args.end)
