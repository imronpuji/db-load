# Setup Grafana & Prometheus (Native Install - macOS)

## 1. Install via Homebrew

```bash
# Install Prometheus
brew install prometheus

# Install Grafana
brew install grafana
```

## 2. Konfigurasi Prometheus

File `prometheus.yml` sudah dibuat di project root. Prometheus akan scrape metrics dari script di port **9100** (script exporter), sedangkan Prometheus web UI berjalan di port **9090**.

## 3. Jalankan Prometheus

```bash
# Start Prometheus dengan konfigurasi dari project
prometheus --config.file=$(pwd)/prometheus.yml --storage.tsdb.path=$(pwd)/prometheus_data
```

Atau sebagai service (background):
```bash
brew services start prometheus
# Edit config: /opt/homebrew/etc/prometheus.yml (atau /usr/local/etc/prometheus.yml)
# Set scrape_configs untuk localhost:9090
```

## 4. Jalankan Grafana

```bash
# Start Grafana
brew services start grafana
```

Atau manual:
```bash
grafana-server --config=/opt/homebrew/etc/grafana/grafana.ini --homepath=/opt/homebrew/share/grafana
```

## 5. Akses Grafana

1. Buka browser: http://localhost:3000
2. Login default:
   - Username: `admin`
   - Password: `admin`
   - (akan diminta ganti password pertama kali)

## 6. Setup Data Source

1. Di Grafana, klik **Configuration** → **Data Sources**
2. Klik **Add data source**
3. Pilih **Prometheus**
4. URL: `http://localhost:9090` (Prometheus web UI port)
5. Klik **Save & Test**

## 7. Import Dashboard

1. Klik **Dashboards** → **Import**
2. Upload file `grafana_dashboard.json` dari project
3. Pilih Prometheus data source yang sudah dibuat
4. Klik **Import**

## 8. Jalankan Load Test

```bash
# Pastikan Prometheus sudah running
# Jalankan load test (metrics akan otomatis di-export ke port 9100)
python load_test.py --scenario ramp-up
```

## 9. Lihat Dashboard

Refresh dashboard di Grafana untuk melihat metrics real-time:
- Latency (p50, p95, p99)
- QPS (Queries Per Second)
- Success/Error rates

## Troubleshooting

### Prometheus tidak bisa scrape metrics
- Pastikan script load test sudah running
- Cek metrics exporter: http://localhost:9100/metrics (harus ada output)
- Cek Prometheus targets: http://localhost:9090/targets (harus show "UP")

### Grafana tidak bisa connect ke Prometheus
- Pastikan Prometheus running: `brew services list`
- Test koneksi: `curl http://localhost:9090/api/v1/query?query=up`

### Port sudah digunakan
- Ganti port metrics exporter di `config.yaml` (prometheus_port: 9100)
- Update `prometheus.yml` dengan port baru di targets
- Restart Prometheus

**Catatan Port:**
- Prometheus Web UI: port 9090 (default)
- Metrics Exporter (script): port 9100 (dari config.yaml)
- Grafana: port 3000 (default)

