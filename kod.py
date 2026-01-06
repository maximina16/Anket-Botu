import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# =======================
# AYARLAR
# =======================
PROFILE_DIR = r"C:\chrome_selenium_profile"   # tek profil, login kalır
DEFAULT_URL = "https://derskayit.cu.edu.tr/Ogrenci/SecilenDersler"

# Hız ayarı
CLICK_DELAY = 0.03
SCROLL_DELAY = 0.02

# Sayfa bekleme
WAIT_SEC = 12

# Kaydet butonu (senin verdiğin ID)
SAVE_AND_RETURN_ID = "ContentPlaceHolderOrtaAlan_ContentPlaceHolderIcerik_ctl00_ctl00_btnKaydetVeAnketleredon"

# Anketler sayfasındaki "Anketi Doldur" butonları (senin verdiğin pattern)
ANKET_BUTTON_XPATH = (
    "//input[@type='submit' and contains(@id,'gridDersanket_btnAnket') "
    "and (contains(@value,'Anketi Doldur') or contains(@name,'btnAnket'))]"
)

# Anket sayfasındaki saat inputları
TXTSAAT_XPATH = "//input[@type='text' and (contains(@id,'txtSaat') or contains(@name,'txtSaat'))]"

driver = None


def log_to(status_cb, msg: str):
    status_cb(msg)


def is_driver_alive(drv):
    try:
        _ = drv.current_url
        return True
    except WebDriverException:
        return False


def ensure_driver(status_cb, url: str):
    """Driver yoksa başlatır, varsa canlıysa aynısını kullanır. URL'e gider."""
    global driver
    os.makedirs(PROFILE_DIR, exist_ok=True)

    if driver is not None and is_driver_alive(driver):
        log_to(status_cb, "Chrome zaten açık. URL'e gidiliyor...")
        try:
            driver.get(url)
            log_to(status_cb, "Hazır.")
        except Exception as e:
            log_to(status_cb, f"Hata: {e}")
        return

    log_to(status_cb, "Chrome başlatılıyor...")
    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.add_argument("--start-maximized")

    try:
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        log_to(status_cb, "Chrome açıldı + URL yüklendi. Hazır.")
    except Exception as e:
        driver = None
        log_to(status_cb, f"Chrome başlatılamadı: {e}")

def wait_for_anket_list_or_none():
    """Anketler listesindeki 'Anketi Doldur' butonları görünür mü?"""
    try:
        WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.XPATH, ANKET_BUTTON_XPATH))
        )
        return True
    except Exception:
        return False


def goto_anket_list(status_cb):
    """
    Anketler listesine gittiğimizi GARANTİ eder.
    1) Zaten listede miyiz?
    2) Sayfadaki link/button metinlerinden 'anket' içereni tıkla
    3) Olmazsa olası URL patikalarını dene
    """
    global driver

    # 1) Zaten listede miyiz?
    if driver.find_elements(By.XPATH, ANKET_BUTTON_XPATH):
        return True
    if wait_for_anket_list_or_none():
        return True

    log_to(status_cb, "Anketler sayfasına geçiliyor... (menü/link aranıyor)")

    # 2) Menü / link tıklama denemeleri
    nav_xpaths = [
        # Linkler
        "//a[contains(translate(normalize-space(.),'ANKET','anket'),'anket')]",
        # Buttonlar
        "//button[contains(translate(normalize-space(.),'ANKET','anket'),'anket')]",
        # Input submit/button value
        "//input[(contains(translate(@value,'ANKET','anket'),'anket') or contains(translate(@title,'ANKET','anket'),'anket'))]",
    ]

    for xp in nav_xpaths:
        try:
            items = driver.find_elements(By.XPATH, xp)
            for it in items:
                try:
                    if it.is_displayed() and it.is_enabled():
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", it)
                        time.sleep(0.2)
                        driver.execute_script("arguments[0].click();", it)

                        if wait_for_anket_list_or_none():
                            log_to(status_cb, "Anketler sayfası bulundu (menü/link ile).")
                            return True
                except Exception:
                    continue
        except Exception:
            continue

    # 3) Olası URL patikalarını dene (domain'i mevcut URL'den çıkarır)
    try:
        cur = driver.current_url
        # https://derskayit.cu.edu.tr/.... -> https://derskayit.cu.edu.tr
        origin = cur.split("//", 1)[0] + "//" + cur.split("//", 1)[1].split("/", 1)[0]
    except Exception:
        origin = "https://derskayit.cu.edu.tr"

    candidates = [
        origin + "/Ogrenci/Anketler",
        origin + "/Ogrenci/Anket",
        origin + "/Ogrenci/DersAnket",
        origin + "/Ogrenci/DersAnketleri",
        origin + "/Ogrenci/Anketlerim",
    ]

    log_to(status_cb, "Menüden bulunamadı, olası URL'ler deneniyor...")
    for u in candidates:
        try:
            driver.get(u)
            time.sleep(0.6)
            if driver.find_elements(By.XPATH, ANKET_BUTTON_XPATH) or wait_for_anket_list_or_none():
                log_to(status_cb, f"Anketler sayfası bulundu: {u}")
                return True
        except Exception:
            continue

    log_to(status_cb, "Anketler sayfasına gidemedim. (URL yanlış/menü yapısı farklı olabilir)")
    log_to(status_cb, f"Şu an URL: {driver.current_url}")
    return False

# ---------- Puan tıklama ----------
def find_labels_for_score(drv, score: int):
    needles = [
        f"({score} Puan)",
        f"{score} Puan",
        f" {score} ",
        f"{score})",
    ]

    labels = drv.find_elements(By.XPATH, "//label")
    hits = []
    for lb in labels:
        txt = (lb.text or "").strip()
        if txt and any(n in txt for n in needles):
            hits.append(lb)
    return hits


def fast_click_elements(drv, elements, status_cb):
    total = len(elements)
    for i, el in enumerate(elements, start=1):
        try:
            drv.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            time.sleep(SCROLL_DELAY)
            drv.execute_script("arguments[0].click();", el)
        except Exception:
            try:
                el.click()
            except Exception:
                pass

        if i % 10 == 0 or i == total:
            log_to(status_cb, f"Tıklandı: {i}/{total}")
        time.sleep(CLICK_DELAY)


def click_score(status_cb, url: str, score: int):
    global driver
    if driver is None or not is_driver_alive(driver):
        ensure_driver(status_cb, url)
    if driver is None:
        return

    try:
        log_to(status_cb, f"{score} puan label'ları aranıyor...")
        hits = find_labels_for_score(driver, score)
        log_to(status_cb, f"Bulunan: {len(hits)}")

        if not hits:
            log_to(status_cb, "0 bulundu.")
            log_to(status_cb, f"URL: {driver.current_url}")
            return

        fast_click_elements(driver, hits, status_cb)
        log_to(status_cb, "Puanlama tamam.")
    except Exception as e:
        log_to(status_cb, f"Hata: {e}")


# ---------- Saat input doldurma ----------
def find_time_inputs(drv):
    els = drv.find_elements(By.XPATH, TXTSAAT_XPATH)

    filtered = []
    for e in els:
        try:
            if e.is_displayed() and e.is_enabled():
                filtered.append(e)
        except Exception:
            pass
    return filtered


def fill_times(status_cb, url: str, times_text: str):
    global driver
    if driver is None or not is_driver_alive(driver):
        ensure_driver(status_cb, url)
    if driver is None:
        return

    times = [t.strip() for t in times_text.splitlines() if t.strip()]
    if not times:
        log_to(status_cb, "Saat kutusu boş.")
        return

    try:
        inputs = find_time_inputs(driver)
        log_to(status_cb, f"txtSaat input sayısı: {len(inputs)}")

        if not inputs:
            log_to(status_cb, "txtSaat input bulunamadı.")
            log_to(status_cb, f"URL: {driver.current_url}")
            return

        n = min(len(inputs), len(times))
        for idx in range(n):
            inp = inputs[idx]
            val = times[idx]

            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
            time.sleep(SCROLL_DELAY)

            try:
                inp.click()
                inp.clear()
                inp.send_keys(val)
                driver.execute_script(
                    "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                    "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                    inp
                )
            except Exception:
                driver.execute_script(
                    "arguments[0].value = arguments[1];"
                    "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                    "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                    inp, val
                )

            if idx % 5 == 0 or idx == n - 1:
                log_to(status_cb, f"Saat yazıldı: {idx+1}/{n}")

            time.sleep(0.05)

        log_to(status_cb, "Saat doldurma tamam.")
    except Exception as e:
        log_to(status_cb, f"Hata: {e}")


# ---------- Kaydet ve Anketlere Dön ----------
def click_save_and_return(status_cb, url: str):
    global driver
    if driver is None or not is_driver_alive(driver):
        ensure_driver(status_cb, url)
    if driver is None:
        return

    try:
        log_to(status_cb, "Kaydet ve Anketlere Dön tıklanıyor...")

        btn = WebDriverWait(driver, WAIT_SEC).until(
            EC.element_to_be_clickable((By.ID, SAVE_AND_RETURN_ID))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        time.sleep(SCROLL_DELAY)
        driver.execute_script("arguments[0].click();", btn)

        # Anketler sayfasına dönüş bekle: "Anketi Doldur" butonlarından biri gelsin
        WebDriverWait(driver, WAIT_SEC).until(
            EC.presence_of_element_located((By.XPATH, ANKET_BUTTON_XPATH))
        )

        log_to(status_cb, "Kaydet ve Anketlere Dön tamam.")
    except Exception as e:
        # Her anket sonrası anket kalmadıysa burada timeout olabilir, o yüzden mesajı netleştiriyoruz
        log_to(status_cb, f"Kaydet hatası/anket listesi bekleme: {e}")


def close_driver(status_cb):
    global driver
    if driver is None:
        log_to(status_cb, "Chrome zaten kapalı.")
        return
    try:
        driver.quit()
    except Exception:
        pass
    driver = None
    log_to(status_cb, "Chrome kapatıldı.")


# ---------- Anketler sayfasında sıradaki anketi aç ----------
def click_next_anket_button(status_cb):
    """
    Anketler listesindeki ilk görünen 'Anketi Doldur' butonuna tıklar.
    Tıklarsa True, yoksa False.
    """
    global driver

    try:
        buttons = driver.find_elements(By.XPATH, ANKET_BUTTON_XPATH)
        target = None
        for b in buttons:
            try:
                if b.is_displayed() and b.is_enabled():
                    target = b
                    break
            except Exception:
                pass

        if not target:
            return False

        log_to(status_cb, "Anketi Doldur tıklanıyor...")
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", target)
        time.sleep(SCROLL_DELAY)
        driver.execute_script("arguments[0].click();", target)

        # Anket sayfasına geçiş: txtSaat inputlarını bekle
        WebDriverWait(driver, WAIT_SEC).until(
            EC.presence_of_element_located((By.XPATH, TXTSAAT_XPATH))
        )
        return True

    except Exception as e:
        log_to(status_cb, f"Anket butonu tıklama/bekleme hatası: {e}")
        return False


# ---------- TAM OTOMATİK: Anket kalmayana kadar ----------
def run_full_automation(status_cb, url: str, score: int, times_text: str):
    global driver
    try:
        log_to(status_cb, "Tam otomatik başladı...")
        ensure_driver(status_cb, url)
        if driver is None:
            return

        # ÖNCE: anketler listesine gerçekten git
        ok = goto_anket_list(status_cb)
        if not ok:
            return

        done = 0
        max_loops = 300  # güvenlik

        for _ in range(max_loops):
            log_to(status_cb, f"Anket aranıyor... (tamamlanan: {done})")

            # Anket kalmadıysa bitir
            if not driver.find_elements(By.XPATH, ANKET_BUTTON_XPATH):
                # bazen geç yüklenir
                if not wait_for_anket_list_or_none():
                    log_to(status_cb, f"Bitti! Toplam doldurulan anket: {done}")
                    return

            # 1) Anketi aç
            has_next = click_next_anket_button(status_cb)
            if not has_next:
                log_to(status_cb, f"Bitti! Toplam doldurulan anket: {done}")
                return

            time.sleep(0.2)

            # 2) Saatleri doldur
            log_to(status_cb, "Saatler yazılıyor...")
            fill_times(status_cb, url, times_text)
            time.sleep(0.2)

            # 3) Puan seç
            log_to(status_cb, f"{score} puan seçiliyor...")
            click_score(status_cb, url, score)
            time.sleep(0.2)

            # 4) Kaydet ve geri dön
            click_save_and_return(status_cb, url)
            done += 1
            time.sleep(0.5)

            # dönüşte tekrar listede olduğumuzu garanti et
            ok = goto_anket_list(status_cb)
            if not ok:
                return

        log_to(status_cb, f"Güvenlik limiti ({max_loops}) aşıldı. Durduruldu. (tamamlanan: {done})")

    except Exception as e:
        log_to(status_cb, f"Tam otomatik hata: {e}")



# =======================
# GUI
# =======================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Anket Botu")
        self.geometry("820x470")
        self.resizable(False, False)

        self.status_var = tk.StringVar(value="Hazır.")

        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(0, weight=1)
        frm.columnconfigure(1, weight=0)

        ttk.Label(frm, text="Anket Otomasyon Botu", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")

        ttk.Label(frm, text="Hedef URL:", font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w", pady=(10, 2))
        self.url_entry = ttk.Entry(frm)
        self.url_entry.insert(0, DEFAULT_URL)
        self.url_entry.grid(row=2, column=0, sticky="we")

        btnrow = ttk.Frame(frm)
        btnrow.grid(row=3, column=0, sticky="w", pady=(10, 8))

        ttk.Button(btnrow, text="Başlat (Chrome Aç + URL)", command=self.on_start).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(btnrow, text="Kapat", command=self.on_close).grid(row=0, column=1)
        ttk.Button(btnrow, text="Kaydet ve Anketlere Dön", command=lambda: self.run_bg(click_save_and_return)).grid(row=0, column=2, padx=(8, 0))

        scoreframe = ttk.LabelFrame(frm, text="Puan Seç (Hızlı)")
        scoreframe.grid(row=4, column=0, sticky="we", pady=(6, 10))

        for i in range(1, 6):
            ttk.Button(
                scoreframe,
                text=f"{i} Puan",
                command=lambda s=i: self.run_bg(click_score, s)
            ).grid(row=0, column=i - 1, padx=6, pady=10)

        timeframe = ttk.LabelFrame(frm, text="Saatleri Yaz (Her satır bir sayı: 2 / 5 / 6 gibi)")
        timeframe.grid(row=5, column=0, sticky="we")

        self.times_box = tk.Text(timeframe, height=6, width=60)
        self.times_box.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.times_box.insert("1.0", "2\n5\n6")

        ttk.Button(timeframe, text="Saatleri Form'a Yaz", command=self.on_fill_times).grid(row=0, column=1, padx=10)

        ttk.Separator(frm).grid(row=6, column=0, sticky="we", pady=10)
        ttk.Label(frm, textvariable=self.status_var, font=("Segoe UI", 10)).grid(row=7, column=0, sticky="w")

        footer = ttk.Label(frm, text="made with love by maxi", font=("Segoe UI", 9))
        footer.grid(row=8, column=0, sticky="e", pady=(10, 0))

        # Yan panel
        side = ttk.LabelFrame(frm, text="Yan Kategori")
        side.grid(row=4, column=1, rowspan=4, sticky="ns", padx=(12, 0), pady=(6, 0))

        ttk.Label(side, text="Tam otomatik çalıştır", font=("Segoe UI", 9)).pack(anchor="w", padx=10, pady=(10, 6))
        ttk.Label(side, text="Puan:", font=("Segoe UI", 9)).pack(anchor="w", padx=10)

        self.auto_score = tk.StringVar(value="3")
        ttk.Combobox(
            side,
            textvariable=self.auto_score,
            values=["1", "2", "3", "4", "5"],
            width=6,
            state="readonly"
        ).pack(anchor="w", padx=10, pady=(0, 10))

        ttk.Button(side, text="TAM OTOMATİK (Anket Bitene Kadar)", command=self.on_full_auto).pack(fill="x", padx=10, pady=(0, 10))

        self.protocol("WM_DELETE_WINDOW", self.on_exit)

    def set_status(self, text):
        self.status_var.set(text)

    def get_url(self):
        url = self.url_entry.get().strip()
        if not url:
            raise ValueError("URL boş olamaz.")
        return url

    def run_bg(self, fn, *args):
        try:
            url = self.get_url()
        except Exception as e:
            messagebox.showwarning("Uyarı", str(e))
            return

        self.set_status("Çalışıyor...")

        def runner():
            fn(self.set_status, url, *args)

        threading.Thread(target=runner, daemon=True).start()

    def on_start(self):
        try:
            url = self.get_url()
        except Exception as e:
            messagebox.showwarning("Uyarı", str(e))
            return

        self.set_status("Başlatılıyor...")
        threading.Thread(target=ensure_driver, args=(self.set_status, url), daemon=True).start()

    def on_fill_times(self):
        try:
            url = self.get_url()
        except Exception as e:
            messagebox.showwarning("Uyarı", str(e))
            return

        times_text = self.times_box.get("1.0", "end").strip()
        self.set_status("Saatler yazılıyor...")
        threading.Thread(target=fill_times, args=(self.set_status, url, times_text), daemon=True).start()

    def on_full_auto(self):
        try:
            url = self.get_url()
        except Exception as e:
            messagebox.showwarning("Uyarı", str(e))
            return

        times_text = self.times_box.get("1.0", "end").strip()
        try:
            score = int(self.auto_score.get())
        except Exception:
            score = 3

        self.set_status("Tam otomatik çalışıyor...")

        def runner():
            run_full_automation(self.set_status, url, score, times_text)

        threading.Thread(target=runner, daemon=True).start()

    def on_close(self):
        self.set_status("Kapatılıyor...")
        threading.Thread(target=close_driver, args=(self.set_status,), daemon=True).start()

    def on_exit(self):
        try:
            if driver is not None and is_driver_alive(driver):
                driver.quit()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
