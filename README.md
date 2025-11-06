# DB Load Testing Script

Python async load tester for PostgreSQL focusing on read queries and connection simulations, with Prometheus/Grafana metrics and multiple scenarios.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set `DATABASE_URL` or edit `config.yaml`.

## Usage

```bash
# Ramp-up from 100 to 10,000 over 5 minutes
python load_test.py --scenario ramp-up

# Sustained 10,000 connections for 10 minutes
python load_test.py --scenario sustained

# Spike pattern
python load_test.py --scenario spike

# Stress increasing steps
python load_test.py --scenario stress
```

Enable Prometheus (default) and view prebuilt Grafana dashboard `grafana_dashboard.json`.

## Notes
- Auto-discovers tables (prefers names containing `event` or `product`).
- Falls back to generic queries if schema lacks expected columns.
- Reports written to `reports/` per `config.yaml`.


