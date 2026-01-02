from __future__ import annotations

from app.pipeline.intake.opportunity_tracker_import import parse_opportunity_tracker_csv, row_to_rfp_and_tracker


def test_parse_opportunity_tracker_csv_finds_header_and_rows() -> None:
    csv_text = (
        ",,,,,,,\n"
        "Opportunity,Point Person,Support Role,Notes,Date Last Confirmed,Mailing?,Question/Answers,Due Date,Announce Date,Funding Arrives (Assume Win Date+30-45 days),Value,Entity,Source,Applying Entity\n"
        "Example Opportunity,Saxon,Cale,Note,,x,https://example.com/qa,1/5/2026,2/28/26,,\"$150,000\",DOE,Google,Federal\n"
    )
    rows = parse_opportunity_tracker_csv(csv_text)
    assert len(rows) == 1
    assert rows[0]["Opportunity"] == "Example Opportunity"
    assert rows[0]["Mailing?"] == "x"


def test_row_to_rfp_and_tracker_normalizes_dates_and_boolean() -> None:
    row = {
        "Opportunity": "Example Opportunity",
        "Point Person": "Saxon",
        "Support Role": "Cale",
        "Notes": "Hello",
        "Date Last Confirmed": "7/7/2025",
        "Mailing?": "x",
        "Question/Answers": "https://example.com/qa",
        "Due Date": "1/5/2026",
        "Announce Date": "2/28/26",
        "Funding Arrives (Assume Win Date+30-45 days)": "Win + 30 days",
        "Value": "$150,000",
        "Entity": "DOE",
        "Source": "Google",
        "Applying Entity": "Federal",
    }
    conv = row_to_rfp_and_tracker(row)
    assert conv["rfpAnalysis"]["title"] == "Example Opportunity"
    assert conv["rfpAnalysis"]["clientName"] == "DOE"
    assert conv["rfpAnalysis"]["submissionDeadline"] == "2026-01-05"
    assert conv["trackerPatch"]["mailing"] is True
    assert conv["trackerPatch"]["announceDate"] == "2026-02-28"
    assert conv["trackerPatch"]["dateLastConfirmed"] == "2025-07-07"


