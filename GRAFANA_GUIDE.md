# 📊 Panduan Dashboard Grafana - Pengambilan Keputusan

## Memahami Metrics

### 🔍 Perbedaan Console vs Grafana

**Console (Real-time Snapshot):**
- `ok=1995 err=0` → Total kumulatif sejak test dimulai
- Update setiap 2 detik dengan angka yang terus bertambah

**Grafana (Rate/Trend):**
- Menampilkan **rate per detik** (errors/second)
- Bukan total kumulatif, tapi kecepatan error
- Lebih berguna untuk melihat tren dan spike

**Contoh:**
- Console: `err=5000` → Total 5000 error sejak mulai
- Grafana: `5000 errors/sec` → Terjadi 5000 error per detik (BAHAYA!)
- Grafana: `50 errors/sec` → Normal untuk load test besar

---

## 📈 Panel Dashboard & Cara Membaca

### 1. 📊 Current QPS (Queries Per Second)
**Apa ini?** Berapa banyak query yang diproses per detik.

**Ambil Keputusan:**
- ✅ **Hijau (< 1000):** Load ringan, masih banyak kapasitas
- ⚠️ **Kuning (1000-5000):** Load sedang, monitor terus
- 🟠 **Orange (5000-10000):** Load tinggi, siap scaling
- 🔴 **Merah (> 10000):** Mendekati limit, perlu action

**Action:**
- QPS turun tiba-tiba? Cek error rate & latency
- QPS stagnan saat load naik? DB sudah saturated

---

### 2. ✅ Success Rate
**Apa ini?** Persentase request yang berhasil (0-100%).

**Ambil Keputusan:**
- ✅ **> 99%:** Excellent, sistem stabil
- ⚠️ **95-99%:** Warning, ada masalah kecil
- 🔴 **< 95%:** Critical, butuh immediate action

**Action:**
- Success rate drop? Lihat error rate & latency
- < 95%? Scale up atau kurangi load

---

### 3. ❌ Error Rate
**Apa ini?** Berapa banyak error per detik (bukan total).

**Ambil Keputusan:**
- ✅ **0-1 errors/sec:** Normal
- ⚠️ **1-10 errors/sec:** Monitor, bisa timeout biasa
- 🟠 **10-100 errors/sec:** Ada masalah, investigate
- 🔴 **> 100 errors/sec:** Critical, stop load test

**Action:**
- Spike errors? Cek connection time & query latency
- Persistent errors? Cek DB logs, connection pool limit

---

### 4. 🔌 Active Connections
**Apa ini?** Jumlah koneksi aktif ke database saat ini.

**Ambil Keputusan:**
- ✅ **< 1000:** Normal
- ⚠️ **1000-5000:** Moderate load
- 🟠 **5000-10000:** High load, approaching war ticket scenario
- 🔴 **> 10000:** Maximum test load, monitor closely

**Action:**
- Connections tinggi tapi QPS rendah? Connection pool exhausted
- Cek RDS max_connections setting

---

### 5. ⚡ Query Latency (Response Time)
**Apa ini?** Berapa lama query selesai diproses.

**Percentiles:**
- **p50 (Median):** 50% user dapat response time ini atau lebih cepat
- **p95:** 95% user dapat response time ini atau lebih cepat
- **p99:** 99% user dapat response time ini atau lebih cepat (worst case)

**Ambil Keputusan:**
- ✅ **p95 < 100ms:** Excellent, user senang
- ⚠️ **p95 100-500ms:** Acceptable, masih ok
- 🟠 **p95 500ms-1s:** Slow, user mulai complain
- 🔴 **p95 > 1s:** Very slow, butuh optimization

**Action:**
- Latency naik terus? Database overloaded atau query lambat
- p99 >> p95? Ada outlier, cek query yang lambat
- Latency spike saat load naik? Butuh index atau scale

---

### 6. 📈 Throughput (QPS Over Time)
**Apa ini?** Grafik QPS dari waktu ke waktu.

**Pola yang Harus Diperhatikan:**
- **Naik bertahap:** Bagus, sistem scale dengan baik
- **Flat line saat load naik:** Database saturated, tidak bisa handle lebih
- **Drop tiba-tiba:** Ada masalah, cek error rate
- **Spike berulang:** Pattern spike test, monitor recovery time

---

### 7. ✅ Success vs ❌ Error Requests
**Apa ini?** Perbandingan request sukses vs error per detik.

**Ambil Keputusan:**
- Error line rendah/flat? Good
- Error spike bersamaan dengan latency spike? Connection timeout
- Error spike tapi latency normal? Application error (SQL, logic)

---

### 8. 🔌 Connection Establishment Time
**Apa ini?** Berapa lama untuk membuka koneksi ke database.

**Ambil Keputusan:**
- ✅ **< 10ms:** Excellent
- ⚠️ **10-50ms:** Normal
- 🟠 **50-200ms:** Slow, cek network/DB
- 🔴 **> 200ms:** Critical, connection pool issue

**Action:**
- Connection time tinggi? DB connection pool penuh atau network issue
- Persistent high connection time? Naikkan max_connections di RDS

---

## 🎯 Skenario Pengambilan Keputusan

### Scenario 1: War Ticket (10k Users Bersamaan)
**Kondisi Ideal:**
- Success Rate: > 99%
- p95 Latency: < 500ms
- Error Rate: < 10/sec
- Active Connections: 8000-10000

**Jika Gagal:**
- Success Rate < 95%? Scale RDS atau optimize query
- Latency > 1s? Tambah read replica atau cache (Redis)
- Error Rate tinggi? Naikkan connection limit

---

### Scenario 2: Spike Test
**Yang Harus Dilihat:**
- Saat spike dimulai: QPS naik, latency tetap?
- Recovery period: Error rate turun kembali?
- Pattern: Spike berulang sistem tetap stabil?

**Red Flags:**
- Latency tidak recovery setelah spike
- Error terus naik setelah spike berakhir
- QPS tidak bisa kembali ke baseline

---

### Scenario 3: Stress Test
**Yang Harus Dilihat:**
- Pada connection berapa sistem mulai degradasi?
- Error rate mulai naik signifikan di berapa koneksi?
- Latency mulai > 1s di level berapa?

**Breaking Point Indicators:**
- Success rate < 95%
- p95 latency > 1s
- Error rate > 100/sec
- QPS flat meskipun connection naik

---

## 🚨 Alert Thresholds (Rekomendasi)

### Critical (Immediate Action)
- Success Rate < 95%
- Error Rate > 100/sec
- p95 Latency > 2s
- p99 Latency > 5s

### Warning (Monitor Closely)
- Success Rate 95-99%
- Error Rate 10-100/sec
- p95 Latency 500ms-1s
- Connection establishment > 200ms

### Info (Normal Operation)
- Success Rate > 99%
- Error Rate < 10/sec
- p95 Latency < 500ms
- Connection time < 50ms

---

## 💡 Tips Membaca Dashboard

1. **Selalu lihat beberapa panel sekaligus:**
   - Latency naik + Error naik = Database overload
   - QPS turun + Error naik = Sistem mulai reject request
   - Connection time naik + Latency normal = Network/Pool issue

2. **Focus pada percentiles, bukan average:**
   - Average bisa menyesatkan karena outlier
   - p95 lebih representatif untuk user experience
   - p99 menunjukkan worst case scenario

3. **Lihat tren, bukan angka sesaat:**
   - Spike sesaat mungkin normal
   - Tren naik terus = ada masalah
   - Pattern berulang = predictable, bisa di-handle

4. **Bandingkan dengan baseline:**
   - Simpan screenshot kondisi normal
   - Bandingkan saat load test
   - Identifikasi delta/perubahan

---

## ✅ Checklist Sebelum Production

- [ ] Success rate > 99% pada sustained load 10k
- [ ] p95 latency < 500ms pada peak load
- [ ] Error rate < 5/sec pada normal operation
- [ ] System recovery < 5 menit setelah spike
- [ ] No memory leak (monitor selama 1 jam)
- [ ] Connection pool tidak exhausted
- [ ] No long-running query (> 15s timeout)
- [ ] Dashboard alert configured & tested


