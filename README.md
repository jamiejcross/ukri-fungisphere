# UKRI Fungisphere

**A live tracker of active UKRI-funded fungal research.**

→ **[View Dashboard](https://jamiejcross.github.io/ukri-fungisphere/)**

---

## What it does

- Displays all active UKRI projects related to fungi, moulds, and mycology
- Identifies projects with a **social science or humanities remit**
- Provides a **keyword filter tab** with pre-built filters for Aspergillus, AMR/antifungal resistance, and social science terms
- Can **auto-refresh** from the live UKRI Gateway to Research (GTR) API
- Data is searchable, sortable, and paginated

## Structure

```
ukri-fungisphere/
├── index.html              # Dashboard (single-file, no build step)
├── update_data.py          # Python script to refresh data from GTR API
├── data/
│   ├── active_mould_fungi_projects.csv        # All fungal projects
│   ├── active_mould_fungi_social_science.csv  # Social science subset
│   └── metadata.json                          # Update timestamp
└── README.md
```

## Running locally

Open `index.html` in a browser. Because data is loaded from local CSV files via `fetch()`, you need to serve it from a local HTTP server rather than opening the file directly:

```bash
# Python (built-in)
python3 -m http.server 8080

# Then visit: http://localhost:8080
```

## Refreshing data from GTR API

### Via the dashboard

Click **Refresh Data** in the top-right corner. This queries the GTR API live in the browser and updates the display (does not write new CSV files).

### Via the Python script

Run the updater to pull fresh data and overwrite the CSV files:

```bash
# Full update (writes new CSVs)
python3 update_data.py

# Preview only — no files written
python3 update_data.py --dry-run
```

No external dependencies are required — the script uses only the Python standard library.

### Automating with cron (optional)

To run a weekly update on macOS/Linux:

```cron
0 6 * * 1  cd /path/to/ukri-fungisphere && python3 update_data.py >> data/update.log 2>&1
```

## Data sources

- [UKRI Gateway to Research (GTR)](https://gtr.ukri.org) — the primary database of UKRI-funded research
- Initial seed data compiled from GTR CSV export, filtered for active fungal projects

## Keyword categories

| Category | Terms |
|----------|-------|
| Aspergillus | Aspergillus, A. fumigatus, Aspergillosis, A. flavus |
| AMR | AMR, antimicrobial resistance, antifungal resistance, drug resistance, azole resistance |
| Social Science | ethnography, policy, governance, multispecies, humanities, housing/mould |

## Social science classification

Projects are classified as having a social science remit if their title, abstract, or impact statement contains terms associated with: social science/sociology, arts/humanities, ethnography/cultural studies, policy/governance, housing and damp/mould, multispecies approaches, or inequality/justice.

---

Built by Jamie Cross, University of Glasgow.
Data: UKRI Gateway to Research.
