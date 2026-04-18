# AgentRewind Demo Video Script

## Goal

Create a short product demo that shows three things in one flow:

1. Uploading a trace file into AgentRewind
2. Seeing the diagnosis identify the broken step
3. Replaying a fix and comparing the repaired output

## Visual Beats

1. Open AgentRewind on the main debugger screen.
2. Click **Import a Run**.
3. Upload `docs/demo/importable_support_refund_trace.json`.
4. Import it with the **AgentRewind** source type.
5. Pause on the diagnosis box once the imported run loads.
6. Replace the retrieval prompt with the corrected handbook-only prompt.
7. Click **Try Fix From Here**.
8. Hold on the compare panel so the repaired branch and final output are visible.

## Voiceover

AgentRewind helps debug broken multi-agent runs instead of just logging them. Here we import a failed support trace from JSON. The tool loads the run, pinpoints the stale policy retrieval step, and explains why the answer drifted. We then patch that one step to use the current handbook. After replaying from the fork point, AgentRewind shows the repaired branch, compares the outputs, and confirms the run now follows the correct 30-day refund policy.
