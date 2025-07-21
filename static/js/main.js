function toggleTheme() {
    const html = document.documentElement;
    const icon = document.getElementById("themeIcon");
    const isDark = html.getAttribute("data-bs-theme") === "dark";
    html.setAttribute("data-bs-theme", isDark ? "light" : "dark");
    icon.classList.toggle("bi-brightness-high-fill", isDark);
    icon.classList.toggle("bi-moon-stars-fill", !isDark);
  }
  
  function confirmDeleteSingle(section, code) {
    if (confirm("Bu barkodu silmek istiyor musunuz?")) {
      const form = document.createElement("form");
      form.method = "POST";
      form.action = "/delete_code";
      form.innerHTML = `
        <input type="hidden" name="section" value="${section}">
        <input type="hidden" name="code" value="${code}">
      `;
      document.body.appendChild(form);
      form.submit();
    }
  }
   
  // Kamera ve Quagga
  let lastSent = "";
  let lastTime = 0;
  
  const video = document.getElementById("preview");
  const canvas = document.getElementById("overlay");
  const log = document.getElementById("log");
  
  navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } })
    .then(stream => {
      video.srcObject = stream;
      return new Promise(resolve => {
        video.addEventListener("loadedmetadata", () => {
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
          resolve();
        });
      });
    })
    .then(() => {
      Quagga.init({
        inputStream: {
          name: "Live",
          type: "LiveStream",
          target: "#preview",
          constraints: {
            facingMode: "environment",
            width: { min: 640 },
            height: { min: 480 }
          }
        },
        decoder: {
          readers: [
            "code_128_reader", "ean_reader", "ean_8_reader",
            "code_39_reader", "upc_reader", "codabar_reader", "i2of5_reader"
          ]
        },
        locate: true,
        locator: {
          patchSize: "large",
          halfSample: false
        },
        numOfWorkers: 1,
        frequency: 25
      }, err => {
        if (err) {
          console.error("Quagga başlatma hatası:", err);
          if (log) log.textContent = "❌ Kamera başlatılamadı: " + err.message;
          return;
        }
        Quagga.start();
        if (log) log.textContent = "📷 Kamera aktif. Barkodu kameraya gösterin.";
      });
  
      Quagga.onProcessed(result => {
        const ctx = Quagga.canvas.ctx.overlay;
        const overlayCanvas = Quagga.canvas.dom.overlay;
        overlayCanvas.width = video.videoWidth;
        overlayCanvas.height = video.videoHeight;
        ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
  
        if (result?.boxes) {
          result.boxes
            .filter(box => box !== result.box)
            .forEach(box => {
              Quagga.ImageDebug.drawPath(box, { x: 0, y: 1 }, ctx, {
                color: "gray", lineWidth: 2
              });
            });
        }
  
        if (result?.box) {
          Quagga.ImageDebug.drawPath(result.box, { x: 0, y: 1 }, ctx, {
            color: "#28a745", lineWidth: 4
          });
        }
  
        if (result?.codeResult?.code) {
          ctx.font = "18px Arial";
          ctx.fillStyle = "green";
          ctx.fillText(result.codeResult.code, 10, 30);
        }
      });
  
      Quagga.onDetected(data => {
        const now = Date.now();
        const code = data.codeResult.code;
        if (code && (code !== lastSent || now - lastTime > 3000)) {
          lastSent = code;
          lastTime = now;
  
          if (log) log.textContent = `✅ Okunan Barkod: ${code}`;
          fetch("/scan", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              code: code,
              section: document.getElementById("section").value
            })
          })
            .then(res => {
              if (!res.ok) {
                console.warn("⚠️ Sunucu hatası:", res.status);
              }
            })
            .catch(err => {
              console.error("İstek hatası:", err);
            });
        }
      });
    })
    .catch(err => {
      console.error("📵 Kamera erişimi başarısız:", err);
      if (log) log.textContent = "❌ Kamera erişimi başarısız: " + err.message;
    });
  
  // Barkod listeleme + sayfalama
  function renderBarcodes(sectionIdRaw, page = 1, perPage = 10) {
    const sectionId = sectionIdRaw.replace(/-/g, "_");
    const allCodes = window.barcodeData[`filtered_${sectionId}`] || window.barcodeData[sectionId] || [];
  
    const listEl = document.getElementById(`list-${sectionId}`);
    const paginationEl = document.getElementById(`pagination-${sectionId}`);
    if (!listEl || !paginationEl) return;
  
    const start = (page - 1) * perPage;
    const sliced = allCodes.slice(start, start + perPage);
  
    listEl.innerHTML = "";
  
    sliced.forEach((entry, idx) => {
      const code = entry?.code || entry || "undefined";
      const timestamp = entry?.timestamp || "-";
      const inputId = `${sectionId}-${start + idx + 1}`;
  
      listEl.insertAdjacentHTML("beforeend", `
        <li class="list-group-item">
          <div class="form-check d-flex justify-content-between w-100 align-items-center">
            <div onclick="showDetails('${sectionIdRaw}', '${code}', '${timestamp}')">
              <input class="form-check-input me-2" type="checkbox" name="codes" value="${code}" id="${inputId}">
              <label class="form-check-label" for="${inputId}">
                <i class="bi bi-upc-scan text-primary me-2"></i>${code}
              </label>
            </div>
            <a href="#" onclick="confirmDeleteSingle('${sectionIdRaw}', '${code}')" class="btn btn-sm btn-outline-danger" title="Tek Sil">
              <i class="bi bi-trash"></i>
            </a>
          </div>
        </li>`);
    });
  
    // Sayfalandırma
    paginationEl.innerHTML = "";
    const totalPages = Math.ceil(allCodes.length / perPage);
    const maxVisiblePages = 5;
    let startPage = Math.max(1, page - Math.floor(maxVisiblePages / 2));
    let endPage = Math.min(totalPages, startPage + maxVisiblePages - 1);
    if (endPage - startPage < maxVisiblePages - 1) {
      startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }
  
    if (page > 1) {
      paginationEl.insertAdjacentHTML("beforeend", `
        <li class="page-item">
          <button class="page-link" onclick="renderBarcodes('${sectionIdRaw}', ${page - 1}, ${perPage})">‹</button>
        </li>
      `);
    }
  
    for (let i = startPage; i <= endPage; i++) {
      const active = i === page ? "active" : "";
      paginationEl.insertAdjacentHTML("beforeend", `
        <li class="page-item ${active}">
          <button class="page-link" onclick="renderBarcodes('${sectionIdRaw}', ${i}, ${perPage})">${i}</button>
        </li>
      `);
    }
  
    if (page < totalPages) {
      paginationEl.insertAdjacentHTML("beforeend", `
        <li class="page-item">
          <button class="page-link" onclick="renderBarcodes('${sectionIdRaw}', ${page + 1}, ${perPage})">›</button>
        </li>
      `);
    }
  }
  
  // Tarihe göre filtreleme
  function applyDateFilter() {
    const startInput = document.getElementById('startDate').value;
    const endInput = document.getElementById('endDate').value;
  
    if (!startInput || !endInput) return;
  
    const start = new Date(startInput);
    const end = new Date(endInput);
    end.setHours(23, 59, 59, 999); // Gün sonuna kadar kapsasın
  
    for (const sec in window.barcodeData) {
      const original = window.barcodeData[sec];
      if (!Array.isArray(original)) continue;
  
      const filtered = original.filter(entry => {
        if (!entry.timestamp) return false;
        const t = new Date(entry.timestamp);
        return !isNaN(t) && t >= start && t <= end;
      });
  
      window.barcodeData[`filtered_${sec}`] = filtered;
      renderBarcodes(sec.replace(/_/g, "-"), 1); // düzeltme: id normalleşmişse düz yaz
    }
  }  
  
  // Barkodları periyodik güncelleme
  setInterval(() => {
    fetch('/get_latest_barcodes')
      .then(res => res.json())
      .then(data => {
        for (const sec in data) {
          window.barcodeData[sec] = data[sec];
          renderBarcodes(sec, 1);
        }
      });
  }, 5000);
  
  // Son 10 barkod listesi
  function updateRecentList() {
    fetch('/get_latest_barcodes')
      .then(res => res.json())
      .then(data => {
        const recentList = document.getElementById('recentList');
        recentList.innerHTML = '';
        const flat = [];
        Object.keys(data).forEach(sec => {
          data[sec].forEach(d => flat.push({section: sec, ...d}));
        });
        flat.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
        flat.slice(0, 10).forEach(entry => {
          const li = document.createElement('li');
          li.className = 'list-group-item';
          li.textContent = `[${entry.section}] ${entry.code} (${entry.timestamp})`;
          recentList.appendChild(li);
        });
      });
  }
  setInterval(updateRecentList, 10000);
  
  // Barkod detay modalı
  function showDetails(section, code, timestamp) {
    const body = document.getElementById('barcodeModalBody');
    body.innerHTML = `<strong>Bölüm:</strong> ${section}<br>
                      <strong>Barkod:</strong> ${code}<br>
                      <strong>Zaman:</strong> ${timestamp}`;
    new bootstrap.Modal(document.getElementById('barcodeModal')).show();
  }
  
  // Arama kutusu için filtreleme
  function filterBarcodes(inputEl, sectionIdRaw) {
    const sectionId = sectionIdRaw.replace(/-/g, "_");
    const allCodes = window.barcodeData[sectionId] || [];
    const filtered = allCodes.filter(entry =>
      entry.code.toLowerCase().includes(inputEl.value.toLowerCase())
    );
    window.barcodeData[`filtered_${sectionId}`] = filtered;
    renderBarcodes(sectionIdRaw, 1);
  }
  
  // Sayfa yüklendiğinde başlat
  document.addEventListener("DOMContentLoaded", () => {
    for (const key in window.barcodeData) {
      if (!key.startsWith("filtered_")) {
        renderBarcodes(key.replace(/_/g, "-"));
      }
    }
    updateRecentList();
  });  