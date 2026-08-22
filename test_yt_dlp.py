import sys
import json
import yt_dlp

def test_yt_dlp(playlist_url):
    print(f"Testing yt-dlp with playlist: {playlist_url}")
    
    ydl_opts = {
        'extract_flat': True,  # 動画本体をダウンロードせずメタデータのみ
        'skip_download': True,
        'verbose': True,
        'cookiesfrombrowser': ('chrome',),
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'android', 'tv']
            }
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
            
            print("Success! Extracted playlist information:")
            print(f"Playlist Title: {info.get('title')}")
            entries = info.get('entries', [])
            print(f"Number of videos: {len(entries)}")
            
            for idx, entry in enumerate(entries[:5], 1):
                title = entry.get('title')
                url = entry.get('url') or f"https://www.youtube.com/watch?v={entry.get('id')}"
                print(f"  {idx}. {title} -> {url}")
            if len(entries) > 5:
                print("  ...")
                
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    # デフォルトの公開プレイリストURL（CCライセンス動画が含まれるテストプレイリスト等）
    url = "https://www.youtube.com/playlist?list=PLt5nFmYEQvV-2MhYc6F_L9q32lU1C_YV-"
    if len(sys.argv) > 1:
        url = sys.argv[1]
    test_yt_dlp(url)
