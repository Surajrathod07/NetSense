"""Rebuild the educational corpus. Keep variants of each scenario in one split."""

from pathlib import Path
import csv

SCENARIOS = {
    "hospital": {
        "CRITICAL": """Patient unresponsive; summon the emergency team
Ventilator failure alarm is active
Oxygen supply interrupted; immediate help required
Bedside monitor reports critical heart rate
Patient collapsed during transfer
Emergency call from the resuscitation bay
Smoke detected in the oxygen store; evacuate immediately
Infusion pump stopped unexpectedly during treatment
Backup power failed in intensive care
Patient monitoring system reports a dangerous pressure drop""",
        "NORMAL": """Shift handover starts at nine
Routine temperature log entered
The supply report is ready for review
Please confirm tomorrow's patient transport schedule
Fire drill completed successfully
Staff meeting moved to the afternoon
Bedside monitor passed scheduled inspection
Patient meal preferences updated
Weekly oxygen stock check is complete
Visitor badges are available at reception""",
    },
    "factory": {
        "CRITICAL": """Machine failure alert; conveyor stopped
Emergency stop activated after a pressure surge
Fire detected in the workshop; evacuate immediately
Cooling pump failed and temperature is rising
Operator trapped near the loading gate
Gas leak detected; immediate assistance required
Security breach detected at the server room
Hydraulic line burst; isolate the equipment
Furnace temperature exceeded the critical limit
Smoke alarm active near the production line""",
        "NORMAL": """Today's maintenance meeting is scheduled for three
Machine inspection completed successfully
Routine conveyor speed log recorded
Weekly equipment report is available
Spare motor delivery confirmed for tomorrow
Emergency stop drill is scheduled next week
Please archive yesterday's production totals
Maintenance schedule has been updated
Shift handover notes are ready
Fire extinguisher inventory was updated""",
    },
    "disaster": {
        "CRITICAL": """Floodwater rising; evacuate residents immediately
People trapped after the bridge collapsed
Fire reported in the shelter; send help
Emergency rescue required near the river
Road submerged and the evacuation convoy is stranded
Landslide has blocked the only escape route
Urgent assistance needed for injured volunteers
Danger of collapse; clear the building immediately
Water supply contaminated; emergency distribution required
Distress call received from an isolated village""",
        "NORMAL": """Weekly relief supply report submitted
Routine shelter occupancy count recorded
Tomorrow's volunteer meeting starts at noon
Food parcel inventory is ready for review
Evacuation drill schedule has been circulated
Weather briefing notes are available
Please confirm the next delivery window
Relief team shift handover completed
Shelter registration desk opens tomorrow
Monthly rescue equipment inspection completed""",
    },
}
LOCATIONS = {
    "hospital": ["Ward A", "Ward B", "ICU desk", "South wing", "North unit", "Annex"],
    "factory": [
        "Block C",
        "Line 7",
        "West plant",
        "Assembly hall",
        "Unit B",
        "Main site",
    ],
    "disaster": [
        "Sector C",
        "East zone",
        "River district",
        "Field post",
        "Zone 2",
        "North camp",
    ],
}
ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    with (ROOT / "data/messages.csv").open("w", newline="", encoding="utf8") as f:
        out = csv.writer(f)
        out.writerow(["text", "label", "domain", "scenario"])
        for domain, labels in SCENARIOS.items():
            for label, scenarios in labels.items():
                for i, phrase in enumerate(scenarios.splitlines()):
                    for location in LOCATIONS[domain]:
                        out.writerow(
                            [
                                f"{location}: {phrase}.",
                                label,
                                domain,
                                f"{domain}-{label}-{i}",
                            ]
                        )
