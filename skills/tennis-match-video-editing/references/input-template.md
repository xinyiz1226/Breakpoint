# Input Template

Use this when the user provides only raw video and minimal instructions.

```text
Please edit this full high-angle amateur tennis match raw video into a final highlight video.

[Input]
- Source video path:
- Source duration:
- Match type (singles/doubles):
- Platform: YouTube long-form

[Editing Goal]
- Target final duration (for example 6-12 min):
- Style balance: high-energy highlights vs documentary match flow:
- Keep key score context? (yes/no):

[Keep Priority]
- Aces/direct serve winners: high/medium/low
- Long rally winners: high/medium/low
- Angle creation winners: high/medium/low
- Net volley winners: high/medium/low
- Deep placement winners: high/medium/low
- High-speed winners: high/medium/low

[Drop Priority]
- Ball pickup / side switch / dead time: strict/normal/loose
- Unforced-error points with no buildup: strict/normal/loose
- Serve faults without valid rally: strict/normal/loose

[Output Constraints]
- Output file format: mp4
- Output directory: same as source video
- Resolution rule: must match source exactly
- Frame-rate rule: keep source fps unless requested
- Language mode: Chinese + English summary

[Execution Path]
- Prefer automatic render first
- Fallback to CapCut/Jianying timeline package if needed
```

Lightweight version:

```text
Source:
Target duration:
Keep priorities:
Drop priorities:
Keep key-score context:
Resolution rule: match source
Output directory: same as source
Execution path: auto first, CapCut fallback
```
