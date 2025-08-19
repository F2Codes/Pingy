import sys, socket, struct, random, time, statistics, ipaddress
from dataclasses import dataclass, field
from typing import List, Optional
from PySide6 import QtCore, QtGui, QtWidgets

# ====== تنظیمات ======
FONT_PATH = "Vazir.ttf"  # مسیر فایل فونت وزیر
FONT_SIZE = 10
DEFAULT_DNS_SERVERS = [
    ("گوگل DNS", "8.8.8.8"),
    ("گوگل DNS 2", "8.8.4.4"),
    ("کلودفلر", "1.1.1.1"),
    ("کلودفلر 2", "1.0.0.1"),
    ("کوآد9", "9.9.9.9"),
    ("کوآد9 2", "149.112.112.112"),
]

# ====== DNS Probe ======
def build_dns_query(qname="example.com"):
    txid = random.getrandbits(16)
    flags = 0x0100
    header = struct.pack("!HHHHHH", txid, flags, 1, 0, 0, 0)
    qname_encoded = b"".join(len(l).to_bytes(1, "big") + l.encode("ascii") for l in qname.split(".")) + b"\x00"
    return header + qname_encoded + struct.pack("!HH", 1, 1)

def udp_dns_probe(ip, timeout=1.0, qname="example.com") -> Optional[float]:
    payload = build_dns_query(qname)
    start = time.perf_counter()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        try:
            s.sendto(payload, (ip, 53))
            _ = s.recvfrom(512)
            return (time.perf_counter() - start) * 1000
        except: return None

@dataclass
class Stats:
    samples: List[float] = field(default_factory=list)
    losses: int = 0
    def row(self):
        if not self.samples and not self.losses: return ["-"]*6
        if not self.samples: return ["-","-","-","100%","-","-"]
        c = len(self.samples)
        avg = sum(self.samples)/c
        jitter = statistics.pstdev(self.samples) if c>1 else 0
        mn, mx = min(self.samples), max(self.samples)
        total = c+self.losses
        loss = f"{(self.losses/total)*100:.0f}%"
        return [f"{mn:.1f}",f"{avg:.1f}",f"{mx:.1f}",loss,f"{jitter:.1f}",str(total)]

# ====== Worker ======
class ProbeWorker(QtCore.QObject):
    progress = QtCore.Signal(str,float)
    loss = QtCore.Signal(str)
    done = QtCore.Signal()
    def __init__(self,targets,count,interval,timeout,qname):
        super().__init__()
        self.targets, self.count, self.interval, self.timeout, self.qname = targets,count,interval,timeout,qname
        self._stop=False
    @QtCore.Slot()
    def run(self):
        for i in range(self.count):
            if self._stop: break
            for _,ip in self.targets:
                if self._stop: break
                rtt=udp_dns_probe(ip,self.timeout,self.qname)
                (self.progress.emit(ip,rtt) if rtt else self.loss.emit(ip))
            if i<self.count-1: QtCore.QThread.msleep(int(self.interval*1000))
        self.done.emit()
    def stop(self): self._stop=True

# ====== Main Window ======
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pingy — پنل پینگ DNS")
        self.resize(800,400)
        self.setLayoutDirection(QtCore.Qt.RightToLeft)
        self._set_font()
        self._build_ui()
        self.targets=[]; self.stats={}
        for n,ip in DEFAULT_DNS_SERVERS: self._add(n,ip)

    def _set_font(self):
        font = QtGui.QFont()
        if QtCore.QFile.exists(FONT_PATH):
            id = QtGui.QFontDatabase.addApplicationFont(FONT_PATH)
            family = QtGui.QFontDatabase.applicationFontFamilies(id)[0]
            font.setFamily(family)
        font.setPointSize(FONT_SIZE)
        self.setFont(font)

    def _build_ui(self):
        self.table=QtWidgets.QTableWidget(0,7)
        self.table.setHorizontalHeaderLabels(["نام/آی‌پی","کمینه","میانگین","بیشینه","از دست‌رفت","جیتر","نمونه‌ها"])
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Stretch)
        self.count=QtWidgets.QSpinBox(); self.count.setValue(10)
        self.interval=QtWidgets.QDoubleSpinBox(); self.interval.setValue(0.5)
        self.timeout=QtWidgets.QDoubleSpinBox(); self.timeout.setValue(1.0)
        self.domain=QtWidgets.QLineEdit("example.com")
        self.add_ip=QtWidgets.QLineEdit(); self.add_name=QtWidgets.QLineEdit()
        self.btn_add=QtWidgets.QPushButton("افزودن"); self.btn_del=QtWidgets.QPushButton("حذف")
        self.btn_start=QtWidgets.QPushButton("شروع"); self.btn_stop=QtWidgets.QPushButton("توقف"); self.btn_stop.setEnabled(False)
        top_layout=QtWidgets.QHBoxLayout()
        for w in [self.count,self.interval,self.timeout,self.domain,self.add_name,self.add_ip,self.btn_add,self.btn_del,self.btn_start,self.btn_stop]:
            top_layout.addWidget(w)
        main_layout=QtWidgets.QVBoxLayout()
        main_layout.addLayout(top_layout); main_layout.addWidget(self.table)
        c=QtWidgets.QWidget(); c.setLayout(main_layout); self.setCentralWidget(c)
        self.btn_add.clicked.connect(self._on_add); self.btn_del.clicked.connect(self._on_del)
        self.btn_start.clicked.connect(self._on_start); self.btn_stop.clicked.connect(self._on_stop)

    def _add(self,n,ip):
        r=self.table.rowCount();self.table.insertRow(r)
        self.table.setItem(r,0,QtWidgets.QTableWidgetItem(f"{n} — {ip}"))
        for c in range(1,7): self.table.setItem(r,c,QtWidgets.QTableWidgetItem("-"))
        self.targets.append((n,ip));self.stats[ip]=Stats()
    def _on_add(self):
        ip=self.add_ip.text().strip();n=self.add_name.text().strip() or "Custom"
        try: ipaddress.ip_address(ip)
        except: return
        self._add(n,ip);self.add_ip.clear()
    def _on_del(self):
        for r in sorted({i.row() for i in self.table.selectionModel().selectedRows()},reverse=True):
            ip=self.table.item(r,0).text().split("—")[-1].strip()
            self.table.removeRow(r);self.targets.pop(r);self.stats.pop(ip,None)
    def _on_start(self):
        self._reset()
        self.thread=QtCore.QThread();self.worker=ProbeWorker(self.targets,self.count.value(),self.interval.value(),self.timeout.value(),self.domain.text())
        self.worker.moveToThread(self.thread);self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._progress);self.worker.loss.connect(self._loss)
        self.worker.done.connect(self._done);self.worker.done.connect(self.thread.quit)
        self.btn_start.setEnabled(False);self.btn_stop.setEnabled(True);self.thread.start()
    def _on_stop(self): self.worker.stop();self.btn_start.setEnabled(True);self.btn_stop.setEnabled(False)
    def _reset(self):
        for s in self.stats.values(): s.samples.clear();s.losses=0
        for r in range(self.table.rowCount()): [self.table.item(r,c).setText("-") for c in range(1,7)]
    def _progress(self,ip,rtt): self.stats[ip].samples.append(rtt);self._refresh(ip)
    def _loss(self,ip): self.stats[ip].losses+=1;self._refresh(ip)
    def _done(self): self.btn_start.setEnabled(True);self.btn_stop.setEnabled(False)
    def _refresh(self,ip):
        for r in range(self.table.rowCount()):
            if self.table.item(r,0).text().endswith(ip):
                vals=self.stats[ip].row()
                for c,v in enumerate(vals,1): self.table.item(r,c).setText(v)

# ====== Run ======
def main():
    app=QtWidgets.QApplication(sys.argv)
    w=MainWindow(); w.show()
    sys.exit(app.exec())

if __name__=="__main__": main()
