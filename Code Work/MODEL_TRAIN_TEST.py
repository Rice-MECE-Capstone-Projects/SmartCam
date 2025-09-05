from ultralytics import YOLO

if __name__ == '__main__':
    model = YOLO('yolov8n.pt')
    model.train(
        data='TEST_Dataset/data.yaml', 
        device = 0,
        epochs=50,
        )
