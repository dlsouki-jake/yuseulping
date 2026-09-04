"""채널의 최근 업로드 목록 조회 (yt-dlp 사용, API 키·OAuth 불필요).

원래는 유튜브 RSS 피드(videos.xml)로 감지할 계획이었으나, 실제로 확인해보니
그 주소가 더 이상 응답하지 않아(404) yt-dlp로 대체함. 채널 정보 조회(channels.py)와
같은 방식이라 별도 설정이 추가로 필요 없음.
"""
import yt_dlp

# 기본(web) 클라이언트로는 최근 유튜브가 "The page needs to be reloaded" 오류를 내는 경우가 있어,
# android 클라이언트를 쓰도록 지정함 (실제로 테스트해서 확인한 우회법).
YDL_EXTRACTOR_ARGS = {"youtube": {"player_client": ["android"]}}


def fetch_recent_videos(channel_url, limit=5):
    """채널의 최근 업로드 영상 목록을 가져온다. [{video_id, title, url}, ...] (재생시간은 미포함, 가볍게 조회)"""
    videos_url = channel_url.rstrip("/") + "/videos"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "playlistend": limit,
        "extractor_args": YDL_EXTRACTOR_ARGS,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(videos_url, download=False)

    videos = []
    for entry in info.get("entries", []) or []:
        video_id = entry.get("id")
        if not video_id:
            continue
        videos.append(
            {
                "video_id": video_id,
                "title": entry.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
        )
    return videos


def fetch_duration_seconds(video_url):
    """영상 하나의 재생시간(초)을 가져온다. 쇼츠 판별에 사용."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extractor_args": YDL_EXTRACTOR_ARGS,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
    return info.get("duration")
