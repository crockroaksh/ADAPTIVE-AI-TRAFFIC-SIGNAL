from .lane_processor import process_multi_lane_videos

def process_quadrant_video(video_path, publish=None, esp32_push=None):
    # Legacy endpoint: treat the same source as a single North lane rather
    # than silently inventing four independent camera feeds.
    return process_multi_lane_videos({"North": video_path}, publish=publish, esp32_push=esp32_push)
