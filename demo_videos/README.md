# 60-second synchronized demo videos

Generate the four clips with:

```bash
python demo_videos/generate_demo_videos.py
```

Then upload these exact files on the Upload page:

- `demo_north.mp4` → North
- `demo_south.mp4` → South
- `demo_east.mp4` → East
- `demo_west.mp4` → West

The filenames beginning with `demo_` intentionally activate **scripted demo mode**. This mode is only for presentation/testing; arbitrary uploads still use YOLO.

Demo timeline:

- 0–14 s: North green
- 15–17 s: North yellow
- 18 s: all red
- 19–38 s: **East green for exactly 20 seconds**
- East ambulance is visible from 15–28 s and confirmed by the project from 16–30 s
- 39–41 s: East yellow
- 42 s: all red
- 43–54 s: South green
- 55–57 s: South yellow
- 58 s: all red
- 59 s: West green

Every clip shows only vehicles moving **toward the camera / stop line**. No outgoing traffic stream is drawn.
