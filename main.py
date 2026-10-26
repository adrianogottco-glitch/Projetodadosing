import sys
import time

try:
    import winsound
except ImportError:
    winsound = None

import cv2
import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class VideoView(QLabel):
    """Exibe o vídeo com zoom pela roda e navegação por arraste."""

    def __init__(self):
        super().__init__("Câmera desligada")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(480, 360)
        self.setStyleSheet("background: #15191f; color: #aab4c0; font-size: 20px; border-radius: 10px;")
        self.setMouseTracking(True)
        self.image = QPixmap()
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self.drag_position = None

    def setPixmap(self, pixmap):
        self.image = QPixmap(pixmap)
        self.update()

    def setText(self, text):
        self.image = QPixmap()
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        super().setText(text)
        self.update()

    def paintEvent(self, event):
        if self.image.isNull():
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        fit = min(self.width() / self.image.width(), self.height() / self.image.height())
        base_width = self.image.width() * fit
        base_height = self.image.height() * fit
        center = QPointF(self.width() / 2, self.height() / 2)
        width = base_width * self.zoom
        height = base_height * self.zoom
        target = QPointF(center.x() - width / 2 + self.pan.x(), center.y() - height / 2 + self.pan.y())
        painter.drawPixmap(int(target.x()), int(target.y()), int(width), int(height), self.image)

    def wheelEvent(self, event):
        if self.image.isNull():
            return
        old_zoom = self.zoom
        self.zoom = max(1.0, min(6.0, old_zoom * (1.2 if event.angleDelta().y() > 0 else 1 / 1.2)))
        center = QPointF(self.width() / 2, self.height() / 2)
        cursor = event.position()
        ratio = self.zoom / old_zoom
        self.pan = QPointF(
            cursor.x() - center.x() - ratio * (cursor.x() - center.x() - self.pan.x()),
            cursor.y() - center.y() - ratio * (cursor.y() - center.y() - self.pan.y()),
        )
        if self.zoom == 1.0:
            self.pan = QPointF(0, 0)
        self.update()
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.zoom > 1:
            self.drag_position = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_position is not None:
            delta = event.position() - self.drag_position
            self.pan += delta
            self.drag_position = event.position()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drag_position is not None:
            self.drag_position = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def reset_zoom(self):
        self.zoom = 1.0
        self.pan = QPointF(0, 0)
        self.update()


class FrequencyChart(QWidget):
    """Gráfico de barras das frequências das somas registradas."""

    def __init__(self):
        super().__init__()
        self.counts = {}
        self.setMinimumHeight(170)
        self.setStyleSheet("background: #151b24; border: 1px solid #3b4655; border-radius: 6px;")

    def set_counts(self, counts):
        self.counts = dict(counts)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#151b24"))
        if not self.counts:
            painter.setPen(QColor("#aab4c0"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Aguardando lançamentos")
            return

        values = sorted(self.counts)
        left, top, right, bottom = 30, 14, 10, 30
        chart_width = max(1, self.width() - left - right)
        chart_height = max(1, self.height() - top - bottom)
        max_count = max(self.counts.values())
        slot_width = chart_width / len(values)
        for index, value in enumerate(values):
            count = self.counts[value]
            bar_height = chart_height * count / max_count
            x = left + index * slot_width + slot_width * 0.18
            y = top + chart_height - bar_height
            width = max(3.0, slot_width * 0.64)
            painter.fillRect(QRectF(x, y, width, bar_height), QColor("#3b82f6"))
            painter.setPen(QColor("#edf2f7"))
            painter.drawText(QRectF(x - 4, y - 20, width + 8, 18),
                             Qt.AlignmentFlag.AlignCenter, str(count))
            painter.setPen(QColor("#aab4c0"))
            value_label = f"{value:g}".replace(".", ",")
            painter.drawText(QRectF(left + index * slot_width, top + chart_height + 4,
                                    slot_width, bottom - 4),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                             value_label)


class WebcamWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Visualizador de webcam")
        self.resize(1200, 820)
        self.setMinimumSize(850, 650)
        self.capture = None
        self.roll_counts = {}
        self.roll_total = 0.0
        self.roll_count = 0
        self._roll_previous_gray = None
        self._roll_last_motion = 0.0
        self._roll_pending_since = 0.0
        self._roll_pending_values = None
        self._roll_motion_pending = True
        self._measurement_status = None
        self._measurement_status_since = 0.0
        self._measurement_warning_played = False

        self.video = VideoView()
        self.pipeline_preview = VideoView()
        self.pipeline_preview.setMinimumSize(480, 150)
        self.pipeline_preview.setText("O resultado do pipeline aparecerá aqui")

        self.camera_select = QComboBox()
        self.camera_select.setMinimumHeight(40)
        self.refresh_button = QPushButton("Procurar câmeras")
        self.refresh_button.setMinimumHeight(40)
        self.reset_zoom_button = QPushButton("Redefinir zoom")
        self.reset_zoom_button.setMinimumHeight(40)
        self.toggle_button = QPushButton("Ligar webcam")
        self.toggle_button.setMinimumHeight(46)
        self.toggle_button.setEnabled(False)
        self.status = QLabel("Selecione uma câmera para começar.")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("color: #aab4c0; padding: 8px 0;")

        panel_title = QLabel("CONTROLE DA CÂMERA")
        panel_title.setStyleSheet("color: #8b98a9; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        camera_label = QLabel("Dispositivo")
        camera_label.setStyleSheet("font-weight: 600; margin-top: 12px;")

        pipeline_title = QLabel("PIPELINE DE IMAGEM")
        pipeline_title.setStyleSheet(
            "color: #8b98a9; font-size: 11px; font-weight: 700; letter-spacing: 1px; margin-top: 18px;"
        )
        pipeline_hint = QLabel("Ative as etapas que deseja aplicar. A prévia mostra o resultado final.")
        pipeline_hint.setWordWrap(True)
        pipeline_hint.setStyleSheet("color: #aab4c0; font-size: 12px;")
        self.grayscale_step = QCheckBox("Converter para preto e branco\n(tons de cinza)")
        self.grayscale_step.setChecked(True)
        self.grayscale_step.setStyleSheet(
            "QCheckBox { color: #edf2f7; spacing: 9px; padding: 8px 2px; } "
            "QCheckBox::indicator { width: 18px; height: 18px; }"
        )
        self.threshold_step = QCheckBox("Aplicar blur e limiarização")
        self.threshold_step.setStyleSheet(
            "QCheckBox { color: #edf2f7; spacing: 9px; padding: 8px 2px; } "
            "QCheckBox::indicator { width: 18px; height: 18px; }"
        )
        self.morphology_step = QCheckBox("Fechamento + abertura morfológica")
        self.morphology_step.setStyleSheet(
            "QCheckBox { color: #edf2f7; spacing: 9px; padding: 8px 2px; } "
            "QCheckBox::indicator { width: 18px; height: 18px; }"
        )
        self.contour_step = QCheckBox("Encontrar contornos e calcular métricas")
        self.contour_step.setStyleSheet(
            "QCheckBox { color: #edf2f7; spacing: 9px; padding: 8px 2px; } "
            "QCheckBox::indicator { width: 18px; height: 18px; }"
        )
        self.contour_info = QPlainTextEdit()
        self.contour_info.setReadOnly(True)
        self.contour_info.setPlaceholderText("As métricas dos contornos aparecerão aqui.")
        self.contour_info.setMaximumHeight(150)
        self.contour_info.setStyleSheet(
            "QPlainTextEdit { background: #151b24; color: #c8d2df; border: 1px solid #3b4655; "
            "border-radius: 6px; font-size: 11px; padding: 5px; }"
        )
        self.validation_step = QCheckBox("Validar dados (caixa aprox. quadrada)")
        self.validation_step.setChecked(True)
        self.validation_step.setStyleSheet(
            "QCheckBox { color: #edf2f7; spacing: 9px; padding: 8px 2px; } "
            "QCheckBox::indicator { width: 18px; height: 18px; }"
        )
        self.min_size_spin = QSpinBox()
        self.min_size_spin.setRange(1, 4096)
        self.min_size_spin.setValue(20)
        self.min_size_spin.setSuffix(" px")
        self.max_size_spin = QSpinBox()
        self.max_size_spin.setRange(1, 4096)
        self.max_size_spin.setValue(300)
        self.max_size_spin.setSuffix(" px")
        self.min_size_spin.valueChanged.connect(self.max_size_spin.setMinimum)
        self.max_size_spin.valueChanged.connect(self.min_size_spin.setMaximum)
        self.validation_info = QPlainTextEdit()
        self.validation_info.setReadOnly(True)
        self.validation_info.setPlaceholderText("A validação dos objetos aparecerá aqui.")
        self.validation_info.setMaximumHeight(120)
        self.validation_info.setStyleSheet(
            "QPlainTextEdit { background: #151b24; color: #c8d2df; border: 1px solid #3b4655; "
            "border-radius: 6px; font-size: 11px; padding: 5px; }"
        )
        self.dice_analysis_step = QCheckBox("Analisar face e contar pontos")
        self.dice_analysis_step.setChecked(True)
        self.dice_analysis_step.setStyleSheet(
            "QCheckBox { color: #edf2f7; spacing: 9px; padding: 8px 2px; } "
            "QCheckBox::indicator { width: 18px; height: 18px; }"
        )
        self.die_select = QComboBox()
        self.die_select.setMinimumHeight(36)
        self.die_select.setToolTip("Escolha qual dado mostrar na visualização das etapas")
        self.dice_info = QPlainTextEdit()
        self.dice_info.setReadOnly(True)
        self.dice_info.setPlaceholderText("Os valores identificados aparecerão aqui.")
        self.dice_info.setMaximumHeight(110)
        self.dice_info.setStyleSheet(
            "QPlainTextEdit { background: #151b24; color: #c8d2df; border: 1px solid #3b4655; "
            "border-radius: 6px; font-size: 11px; padding: 5px; }"
        )
        self.roll_chart = FrequencyChart()
        self.roll_summary = QLabel("Jogadas válidas: 0 | Média geral: 0,0")
        self.roll_summary.setWordWrap(True)
        self.roll_summary.setStyleSheet("color: #c8d2df; font-size: 12px; padding: 4px 0;")
        self.roll_hint = QLabel("O registro automático aguarda movimento e uma leitura estável.")
        self.roll_hint.setWordWrap(True)
        self.roll_hint.setStyleSheet("color: #8592a3; font-size: 11px;")
        self.clear_rolls_button = QPushButton("Zerar estatísticas")
        self.clear_rolls_button.setMinimumHeight(36)
        threshold_row = QHBoxLayout()
        threshold_row.setContentsMargins(24, 0, 0, 0)
        threshold_label = QLabel("Threshold: 190")
        threshold_label.setMinimumWidth(105)
        threshold_label.setStyleSheet("color: #aab4c0; font-size: 12px;")
        self.threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.threshold_slider.setRange(0, 255)
        self.threshold_slider.setValue(190)
        self.threshold_slider.setToolTip("Define o valor de threshold entre 0 e 255")
        self.threshold_slider.valueChanged.connect(
            lambda value: threshold_label.setText(f"Threshold: {value}")
        )
        threshold_row.addWidget(threshold_label)
        threshold_row.addWidget(self.threshold_slider, 1)
        self.toggle_button.setStyleSheet(
            "QPushButton { background: #2563eb; color: white; border: 0; border-radius: 6px; "
            "font-weight: 600; padding: 8px; } QPushButton:hover { background: #1d4ed8; } "
            "QPushButton:disabled { background: #354052; color: #8893a3; }"
        )
        self.refresh_button.setStyleSheet(
            "QPushButton { background: #273244; color: #e5eaf1; border: 0; border-radius: 6px; "
            "padding: 8px; } QPushButton:hover { background: #344258; }"
        )

        panel = QVBoxLayout()
        panel.setSpacing(12)
        panel.setContentsMargins(22, 24, 22, 24)
        panel.addWidget(panel_title)
        panel.addWidget(camera_label)
        panel.addWidget(self.camera_select)
        panel.addWidget(self.refresh_button)
        panel.addSpacing(10)
        panel.addWidget(self.toggle_button)
        panel.addWidget(self.reset_zoom_button)
        panel.addWidget(self.status)
        panel.addWidget(pipeline_title)
        panel.addWidget(pipeline_hint)
        panel.addWidget(self.grayscale_step)
        panel.addWidget(self.threshold_step)
        panel.addLayout(threshold_row)
        panel.addWidget(self.morphology_step)
        panel.addWidget(self.contour_step)
        panel.addWidget(self.contour_info)
        panel.addWidget(self.validation_step)
        size_row = QHBoxLayout()
        size_row.setContentsMargins(24, 0, 0, 0)
        size_row.addWidget(QLabel("Mínimo"))
        size_row.addWidget(self.min_size_spin)
        size_row.addWidget(QLabel("Máximo"))
        size_row.addWidget(self.max_size_spin)
        panel.addLayout(size_row)
        square_hint = QLabel("Largura e altura devem estar dentro dos limites. Proporção aceita: 0,65–1,50.")
        square_hint.setWordWrap(True)
        square_hint.setStyleSheet("color: #8592a3; font-size: 11px;")
        panel.addWidget(square_hint)
        panel.addWidget(self.validation_info)
        panel.addWidget(self.dice_analysis_step)
        panel.addWidget(self.die_select)
        panel.addWidget(self.dice_info)
        panel.addWidget(QLabel("FREQUÊNCIA DA MÉDIA DOS DOIS DADOS"))
        panel.addWidget(self.roll_chart)
        panel.addWidget(self.roll_summary)
        panel.addWidget(self.roll_hint)
        panel.addWidget(self.clear_rolls_button)
        zoom_hint = QLabel("Zoom: rode o scroll sobre a imagem.\nArraste para mover a área ampliada.")
        zoom_hint.setWordWrap(True)
        zoom_hint.setStyleSheet("color: #8592a3; font-size: 12px;")
        panel.addWidget(zoom_hint)
        panel.addStretch()
        panel_widget = QWidget()
        panel_widget.setLayout(panel)
        panel_widget.setMinimumWidth(250)
        panel_widget.setMaximumWidth(340)
        panel_widget.setStyleSheet(
            "QWidget { background: #202833; color: #edf2f7; } "
            "QComboBox { background: #151b24; color: #edf2f7; border: 1px solid #3b4655; "
            "border-radius: 6px; padding: 8px; }"
        )
        panel_scroll = QScrollArea()
        panel_scroll.setWidgetResizable(True)
        panel_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        panel_scroll.setMinimumWidth(270)
        panel_scroll.setMaximumWidth(360)
        panel_scroll.setWidget(panel_widget)

        video_area = QWidget()
        video_layout = QVBoxLayout(video_area)
        video_layout.setContentsMargins(20, 20, 12, 20)
        video_layout.setSpacing(8)
        camera_title = QLabel("WEBCAM AO VIVO")
        camera_title.setStyleSheet("color: #8b98a9; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        result_title = QLabel("RESULTADO DO PIPELINE")
        result_title.setStyleSheet("color: #8b98a9; font-size: 11px; font-weight: 700; letter-spacing: 1px;")
        video_layout.addWidget(camera_title)
        video_layout.addWidget(self.video, 3)
        video_layout.addWidget(result_title)
        video_layout.addWidget(self.pipeline_preview, 2)
        video_area.setStyleSheet("background: #11151a;")

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(video_area, 1)
        layout.addWidget(panel_scroll)
        root = QWidget()
        root.setLayout(layout)
        root.setStyleSheet("background: #11151a;")
        self.setCentralWidget(root)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.show_frame)
        self.refresh_button.clicked.connect(self.find_cameras)
        self.toggle_button.clicked.connect(self.toggle_camera)
        self.reset_zoom_button.clicked.connect(self.video.reset_zoom)
        self.clear_rolls_button.clicked.connect(self.reset_roll_statistics)
        self.camera_select.currentIndexChanged.connect(self.camera_changed)

        self.find_cameras()

    def find_cameras(self):
        was_running = self.capture is not None
        self.stop_camera()
        self.camera_select.blockSignals(True)
        self.camera_select.clear()
        found = []
        # Índices são testados porque o OpenCV não oferece uma lista universal
        # de dispositivos; webcams acessíveis costumam aparecer nos primeiros.
        for index in range(10):
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(index)
            if cap.isOpened():
                ok, _ = cap.read()
                if ok:
                    found.append(index)
            cap.release()
        for index in found:
            self.camera_select.addItem(f"Câmera {index}", index)
        self.camera_select.blockSignals(False)
        self.toggle_button.setEnabled(bool(found))
        if found:
            self.status.setText(f"{len(found)} câmera(s) encontrada(s).")
            if was_running:
                self.start_camera()
        else:
            self.status.setText("Nenhuma câmera encontrada. Verifique a conexão e tente novamente.")
            self.video.setText("Câmera desligada")

    def camera_changed(self):
        if self.capture is not None:
            self.start_camera()

    def toggle_camera(self):
        if self.capture is None:
            self.start_camera()
        else:
            self.stop_camera()

    def start_camera(self):
        self.stop_camera()
        index = self.camera_select.currentData()
        if index is None:
            return
        self.capture = cv2.VideoCapture(index, cv2.CAP_DSHOW) if sys.platform == "win32" else cv2.VideoCapture(index)
        if not self.capture.isOpened():
            self.capture.release()
            self.capture = None
            QMessageBox.warning(self, "Webcam", f"Não foi possível abrir a câmera {index}.")
            self.toggle_button.setText("Ligar webcam")
            return
        self.toggle_button.setText("Desligar webcam")
        self.camera_select.setEnabled(False)
        self.status.setText(f"Câmera {index} ligada.")
        self.timer.start(30)

    def stop_camera(self):
        self.timer.stop()
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        if hasattr(self, "toggle_button"):
            self.toggle_button.setText("Ligar webcam")
            self.camera_select.setEnabled(True)
        if hasattr(self, "video"):
            self.video.clear()
            self.video.setText("Câmera desligada")
            self.pipeline_preview.clear()
            self.pipeline_preview.setText("O resultado do pipeline aparecerá aqui")

    def analyze_die(self, source, contour, bounds):
        x, y, width, height = bounds
        roi = source[y:y + height, x:x + width].copy()
        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        # O contorno validado delimita a face e impede que o fundo do ROI vire ponto.
        face_mask = np.zeros((height, width), dtype=np.uint8)
        cv2.drawContours(face_mask, [contour], -1, 255, cv2.FILLED, offset=(-x, -y))
        gray_blur = cv2.GaussianBlur(gray_roi, (3, 3), 0)
        _, inverted = cv2.threshold(gray_blur, 130, 255, cv2.THRESH_BINARY_INV)
        inverted = cv2.bitwise_and(inverted, face_mask)
        opening_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        opened = cv2.morphologyEx(inverted, cv2.MORPH_OPEN, opening_kernel, iterations=1)
        pip_contours, _ = cv2.findContours(opened.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        accepted = []
        roi_area = width * height
        for pip in pip_contours:
            area = cv2.contourArea(pip)
            px, py, pw, ph = cv2.boundingRect(pip)
            if pw == 0 or ph == 0:
                continue
            aspect = pw / ph
            area_fraction = area / roi_area if roi_area else 0
            extent = area / (pw * ph)
            if 0.002 <= area_fraction <= 0.12 and 0.60 <= aspect <= 1.7 and extent >= 0.45:
                accepted.append(pip)

        points_view = cv2.bitwise_and(roi, roi, mask=face_mask)
        cv2.drawContours(points_view, accepted, -1, (0, 230, 120), 2)
        stages = [
            ("ROI recortada", roi),
            ("Máscara da face", face_mask),
            ("Blur + pixels escuros < 130", inverted),
            ("Abertura", opened),
            (f"Pontos aceitos: {len(accepted)}", points_view),
        ]
        return len(accepted), self.make_diagnostic_montage(stages)

    @staticmethod
    def make_diagnostic_montage(stages):
        tile_width, image_height, title_height = 160, 140, 30
        tiles = []
        for title, image in stages:
            if image.ndim == 2:
                image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
            resized = cv2.resize(image, (tile_width, image_height), interpolation=cv2.INTER_AREA)
            tile = cv2.copyMakeBorder(
                resized, title_height, 0, 0, 0, cv2.BORDER_CONSTANT, value=(25, 31, 40)
            )
            cv2.putText(
                tile, title, (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.43,
                (235, 242, 250), 1, cv2.LINE_AA,
            )
            tiles.append(tile)
        return cv2.hconcat(tiles)

    def show_image(self, frame, target):
        if frame.ndim == 2:
            height, width = frame.shape
            image = QImage(frame.data, width, height, width, QImage.Format.Format_Grayscale8).copy()
        else:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            height, width, channels = frame.shape
            image = QImage(frame.data, width, height, channels * width, QImage.Format.Format_RGB888).copy()
        target.setPixmap(QPixmap.fromImage(image))

    def update_roll_tracker(self, source, valid_dice):
        """Registra a soma após movimento seguido por uma leitura estável."""
        now = time.monotonic()
        gray = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (160, 90), interpolation=cv2.INTER_AREA)
        if self._roll_previous_gray is not None:
            difference = cv2.absdiff(small, self._roll_previous_gray)
            motion_ratio = np.count_nonzero(difference > 28) / difference.size
            if motion_ratio > 0.012:
                self._roll_last_motion = now
                self._roll_motion_pending = True
                self._roll_pending_since = now
        self._roll_previous_gray = small

        if len(valid_dice) != 2:
            if self._measurement_status != len(valid_dice):
                self._measurement_status = len(valid_dice)
                self._measurement_status_since = now
                self._measurement_warning_played = False
            elif not self._measurement_warning_played and now - self._measurement_status_since >= 0.8:
                self.play_measurement_sound(success=False)
                self._measurement_warning_played = True
            self._roll_pending_values = None
            self._roll_pending_since = now
            return

        self._measurement_status = 2
        self._measurement_warning_played = False

        values = tuple(sorted(die["value"] for die in valid_dice))
        if values != self._roll_pending_values:
            self._roll_pending_values = values
            self._roll_pending_since = now

        stable_since = max(self._roll_last_motion, self._roll_pending_since)
        if values and self._roll_motion_pending and now - stable_since >= 0.9:
            average = round(sum(values) / 2 * 2) / 2
            self.roll_counts[average] = self.roll_counts.get(average, 0) + 1
            self.roll_total += average
            self.roll_count += 1
            self._roll_motion_pending = False
            self.play_measurement_sound(success=True)
            self.roll_chart.set_counts(self.roll_counts)
            general_average = self.roll_total / self.roll_count
            self.roll_summary.setText(
                f"Jogadas válidas: {self.roll_count} | "
                f"Média geral: {general_average:.2f}".replace(".", ",")
            )

    @staticmethod
    def play_measurement_sound(success):
        try:
            if winsound is not None:
                winsound.MessageBeep(winsound.MB_OK if success else winsound.MB_ICONHAND)
            else:
                QApplication.beep()
        except Exception:
            QApplication.beep()

    def reset_roll_statistics(self):
        self.roll_counts.clear()
        self.roll_total = 0.0
        self.roll_count = 0
        self._roll_motion_pending = False
        self.roll_chart.set_counts(self.roll_counts)
        self.roll_summary.setText("Jogadas válidas: 0 | Média geral: 0,0")

    def show_frame(self):
        if self.capture is None:
            return
        ok, frame = self.capture.read()
        if not ok:
            self.status.setText("N?o foi poss?vel receber imagem da c?mera.")
            self.stop_camera()
            return

        source = frame.copy()
        if self.grayscale_step.isChecked():
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self.threshold_step.isChecked():
            if frame.ndim == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blur = cv2.GaussianBlur(frame, (5, 5), 0)
            _, frame = cv2.threshold(
                blur, self.threshold_slider.value(), 255, cv2.THRESH_BINARY
            )
        if self.morphology_step.isChecked():
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            closing = cv2.morphologyEx(frame, cv2.MORPH_CLOSE, kernel, iterations=2)
            frame = cv2.morphologyEx(closing, cv2.MORPH_OPEN, kernel, iterations=1)

        needs_objects = (
            self.contour_step.isChecked()
            or self.validation_step.isChecked()
            or self.dice_analysis_step.isChecked()
        )
        if not needs_objects:
            self.contour_info.clear()
            self.validation_info.clear()
            self.die_select.clear()
            self.dice_info.clear()
            self.show_image(frame, self.pipeline_preview)
            self.show_image(source, self.video)
            return

        # Procura os pontos escuros diretamente na imagem; n?o segmenta a face
        # branca, que pode se unir ao dado vizinho ou aos reflexos da mesa.
        gray_source = cv2.cvtColor(source, cv2.COLOR_BGR2GRAY)
        gray_source = cv2.GaussianBlur(gray_source, (3, 3), 0)
        # CLAHE reduz o efeito da iluminação desigual entre lados da mesa.
        local_contrast = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = local_contrast.apply(gray_source)
        pip_mask = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 31, 9
        )
        pip_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        pip_mask = cv2.morphologyEx(pip_mask, cv2.MORPH_OPEN, pip_kernel)
        pip_contours, _ = cv2.findContours(
            pip_mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        pips = []
        for contour in pip_contours:
            area = cv2.contourArea(contour)
            if not 5 <= area <= 400:
                continue
            x, y, width, height = cv2.boundingRect(contour)
            if width == 0 or height == 0:
                continue
            aspect = width / height
            perimeter = cv2.arcLength(contour, True)
            circularity = 4 * np.pi * area / (perimeter * perimeter) if perimeter else 0
            extent = area / (width * height)
            if not (0.55 <= aspect <= 1.8 and circularity >= 0.35 and extent >= 0.40):
                continue
            # Um pip deve estar cercado pela face clara do dado. A textura da
            # mesa produz pontos escuros, mas normalmente não tem esse anel claro.
            padding = max(4, int(max(width, height) * 0.7))
            x0, y0 = max(0, x - padding), max(0, y - padding)
            x1 = min(gray.shape[1], x + width + padding)
            y1 = min(gray.shape[0], y + height + padding)
            gray_patch = gray_source[y0:y1, x0:x1]
            mask_patch = pip_mask[y0:y1, x0:x1]
            ring = np.ones(gray_patch.shape, dtype=bool)
            inner_x0 = max(0, x - x0 - 2)
            inner_y0 = max(0, y - y0 - 2)
            inner_x1 = min(gray_patch.shape[1], x + width - x0 + 2)
            inner_y1 = min(gray_patch.shape[0], y + height - y0 + 2)
            ring[inner_y0:inner_y1, inner_x0:inner_x1] = False
            bright_face = gray_patch[ring & (mask_patch == 0)]
            ring_coverage = len(bright_face) / max(1, int(ring.sum()))
            pip_brightness = float(np.mean(gray_source[y:y + height, x:x + width]))
            face_mean = float(np.mean(bright_face)) if len(bright_face) else 0.0
            contrast = face_mean - pip_brightness
            if (ring_coverage < 0.60 or not len(bright_face)
                    or face_mean < 155
                    or contrast < 22):
                continue
            moments = cv2.moments(contour)
            if moments["m00"] == 0:
                continue
            center = (moments["m10"] / moments["m00"], moments["m01"] / moments["m00"])
            pips.append({"contour": contour, "center": center, "x": x, "y": y,
                         "width": width, "height": height, "area": area,
                         "quality": circularity * ring_coverage * contrast})

        # Remove duplicate contours centered on the same dark pip.
        pips.sort(key=lambda pip: pip["area"], reverse=True)
        unique_pips = []
        for pip in pips:
            if any(
                np.linalg.norm(np.subtract(pip["center"], prior["center"]))
                < max(8.0, 0.9 * max(pip["width"], pip["height"]))
                for prior in unique_pips
            ):
                continue
            unique_pips.append(pip)
        pips = unique_pips

        # Complete-link agrupamento: pontos do mesmo dado ficam a at? 55 px
        # entre si. O limite de seis impede unir grupos grandes de dados vizinhos.
        clusters = [[index] for index in range(len(pips))]
        while True:
            best_pair = None
            best_distance = float("inf")
            for first in range(len(clusters)):
                for second in range(first + 1, len(clusters)):
                    combined = clusters[first] + clusters[second]
                    if len(combined) > 6:
                        continue
                    max_distance = max(
                        np.linalg.norm(np.subtract(pips[a]["center"], pips[b]["center"]))
                        for offset, a in enumerate(combined)
                        for b in combined[offset + 1:]
                    )
                    if max_distance <= 55 and max_distance < best_distance:
                        best_pair = (first, second)
                        best_distance = max_distance
            if best_pair is None:
                break
            first, second = best_pair
            clusters[first] += clusters[second]
            del clusters[second]

        # Unifica grupos muito próximos que foram partidos dentro da mesma face.
        # O limite de centro evita fundir dois dados apenas por terem caixas
        # ampliadas sobrepostas. Se houver pontos falsos extras, mantém os seis
        # candidatos com melhor circularidade e contraste.
        while True:
            merge_pair = None
            for first in range(len(clusters)):
                for second in range(first + 1, len(clusters)):
                    combined = clusters[first] + clusters[second]
                    if len(combined) > 8:
                        continue
                    centers = [np.array(pips[index]["center"]) for index in clusters[first]]
                    other_centers = [np.array(pips[index]["center"]) for index in clusters[second]]
                    center_a = np.mean(centers, axis=0)
                    center_b = np.mean(other_centers, axis=0)
                    if np.linalg.norm(center_a - center_b) <= 22:
                        merge_pair = (first, second)
                        break
                if merge_pair:
                    break
            if merge_pair is None:
                break
            first, second = merge_pair
            clusters[first] += clusters[second]
            del clusters[second]

        clusters = [
            sorted(cluster, key=lambda index: pips[index]["quality"], reverse=True)[:6]
            for cluster in clusters
        ]

        # Valida a disposição dos valores 5 e 6 numa grade de faces 3x3.
        # Se seis candidatos formarem melhor o padrão de cinco, descarta o
        # ponto extra que veio da textura/iluminação.
        image_height, image_width = source.shape[:2]
        padding = 22
        dice = []
        for cluster in clusters:
            if not 1 <= len(cluster) <= 6:
                continue
            points = [pips[index] for index in cluster]
            left = max(0, min(point["x"] for point in points) - padding)
            top = max(0, min(point["y"] for point in points) - padding)
            right = min(image_width, max(point["x"] + point["width"] for point in points) + padding)
            bottom = min(image_height, max(point["y"] + point["height"] for point in points) + padding)
            width, height = right - left, bottom - top
            aspect = width / height if height else 0
            is_valid = (
                self.min_size_spin.value() <= width <= self.max_size_spin.value()
                and self.min_size_spin.value() <= height <= self.max_size_spin.value()
                and 0.65 <= aspect <= 1.5
            )
            dice.append({"indices": cluster, "value": len(cluster), "box": (left, top, width, height),
                         "valid": is_valid})
        dice.sort(key=lambda die: (die["box"][1], die["box"][0]))
        valid_dice = [die for die in dice if die["valid"]]
        if self.dice_analysis_step.isChecked():
            self.update_roll_tracker(source, valid_dice)

        display_frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR) if frame.ndim == 2 else frame.copy()
        if self.contour_step.isChecked():
            cv2.drawContours(display_frame, [pip["contour"] for pip in pips], -1, (255, 190, 0), 1)
            contour_lines = [f"Pontos escuros: {len(pips)} | grupos: {len(dice)}"]
            for index, pip in enumerate(pips, 1):
                contour_lines.append(f"Ponto {index}: ?rea {pip['area']:.0f} px")
            self.contour_info.setPlainText("\n".join(contour_lines))
        else:
            self.contour_info.clear()

        if self.validation_step.isChecked():
            validation_lines = [f"Grupos v?lidos: {len(valid_dice)} de {len(dice)}"]
            for index, die in enumerate(dice, 1):
                x, y, width, height = die["box"]
                state = "V?LIDO" if die["valid"] else "INV?LIDO"
                validation_lines.append(
                    f"{index}: {state} ? {die['value']} pontos, {width}?{height} px"
                )
                if die["valid"]:
                    cv2.rectangle(display_frame, (x, y), (x + width, y + height), (0, 220, 90), 1)
            self.validation_info.setPlainText("\n".join(validation_lines))
        else:
            self.validation_info.clear()

        selected = max(0, self.die_select.currentIndex())
        self.die_select.blockSignals(True)
        self.die_select.clear()
        for index, die in enumerate(valid_dice, 1):
            self.die_select.addItem(f"Dado {index} ? valor {die['value']}")
        if valid_dice:
            selected = min(selected, len(valid_dice) - 1)
            self.die_select.setCurrentIndex(selected)
        self.die_select.blockSignals(False)

        if self.dice_analysis_step.isChecked():
            if len(valid_dice) < 2:
                missing = 2 - len(valid_dice)
                result_lines = [
                    f"AVISO: detectei {len(valid_dice)} dado(s); falta(m) {missing} para completar 2."
                ]
            elif len(valid_dice) > 2:
                result_lines = [
                    f"AVISO: detectei {len(valid_dice)} dados; mantenha exatamente 2 no enquadramento."
                ]
            else:
                current_average = sum(die["value"] for die in valid_dice) / 2
                result_lines = [
                    f"Dois dados detectados | média desta jogada: {current_average:.1f}".replace(".", ",")
                ]
            for index, die in enumerate(valid_dice, 1):
                result_lines.append(f"Dado {index}: valor {die['value']} ({die['value']} pontos)")
                x, y, width, height = die["box"]
                color = (0, 230, 120) if index - 1 == selected else (0, 190, 255)
                cv2.rectangle(display_frame, (x, y), (x + width, y + height), color, 2)
                cv2.putText(display_frame, f"Dado {index}: {die['value']}", (x, max(22, y - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)
                cv2.rectangle(source, (x, y), (x + width, y + height), color, 2)
                cv2.putText(source, f"Dado {index}: {die['value']}", (x, max(22, y - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)
            self.dice_info.setPlainText("\n".join(result_lines))
        else:
            self.dice_info.clear()

        self.show_image(display_frame, self.pipeline_preview)
        self.show_image(source, self.video)

    def closeEvent(self, event):
        self.stop_camera()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WebcamWindow()
    window.show()
    sys.exit(app.exec())
