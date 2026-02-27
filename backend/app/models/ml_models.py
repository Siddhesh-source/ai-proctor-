from ultralytics import YOLO


yolo = YOLO("yolov8l.pt")
yolo.overrides["conf"] = 0.20
