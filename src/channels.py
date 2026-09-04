"""채널 URL 검증 + 채널 정보 조회 (yt-dlp 사용, API 키 불필요)."""
import yt_dlp

from config_store import load_config, save_config


def fetch_channel_info(url):
    """채널 URL에서 채널 ID/이름을 가져온다. 실패하면 ValueError를 낸다."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "playlistend": 1,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    channel_id = info.get("channel_id") or info.get("id")
    title = info.get("channel") or info.get("title") or info.get("uploader")
    if not channel_id or not title:
        raise ValueError("채널 정보를 찾을 수 없어요. URL을 다시 확인해주세요.")

    return {"id": channel_id, "title": title, "url": url}


def add_channel(url):
    config = load_config()

    for ch in config["channels"]:
        if ch["url"] == url:
            return config["channels"]  # 이미 등록된 채널

    info = fetch_channel_info(url)
    config["channels"].append(info)
    save_config(config)
    return config["channels"]


def remove_channel(channel_id):
    config = load_config()
    config["channels"] = [ch for ch in config["channels"] if ch["id"] != channel_id]
    save_config(config)
    return config["channels"]
