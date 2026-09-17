import time
from PIL import Image
import io
from ultralytics import YOLO

class YOLOService:
    def __init__(self, model_name: str = "yolov8n.pt"):
    
        self.model = YOLO(model_name)

    def predict(self, image_bytes: bytes, conf_threshold: float = 0.25):
   
        image = Image.open(io.BytesIO(image_bytes))

        start_time = time.perf_counter()
        results = self.model.predict(source=image, conf=conf_threshold, verbose=False)
        inference_time = round(time.perf_counter() - start_time, 4)

        detections = []
        result = results[0]
        
        for box in result.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cls_id = int(box.cls[0])
            label = result.names[cls_id]
            conf = float(box.conf[0])

            detections.append({
                "class": label,
                "confidence": round(conf, 4),
                "bbox": [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)]
            })

        return {
            "count": len(detections),
            "inference_time_seconds": inference_time,
            "confidence_threshold": conf_threshold,
            "detections": detections
        }