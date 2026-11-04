from ai.screenshot_analyzer import default_screenshot_analyzer
from input.screenshot_models import ScreenshotMetadata

meta = ScreenshotMetadata(
    filename='screen.png',
    format='PNG',
    width=500,
    height=300,
    file_size=1000,
    sha256='0'*64,
    aspect_ratio=1.66
)
text = 'The image shows a Windows Update error message displayed on a computer screen. The message reads "There were some problems installing updates." The error code 0x80070422 is displayed.'
data = default_screenshot_analyzer._synthesize_structured_json_from_raw_text(text)
ev = default_screenshot_analyzer._build_evidence_from_json(data, meta)
hints = default_screenshot_analyzer.mapper.map_evidence_to_hints(ev, data['suggested_diagnostic_areas'])

print('FACTS:', data['visible_facts_summary'])
print('ERRORS:', ev.detected_error_codes)
print('APPLICATIONS:', ev.detected_applications)
print('OBSERVATIONS:', [(o.category, o.text) for o in ev.observations])
print('HINTS:', [h.tool_name for h in hints])
