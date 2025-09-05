from ultralytics import YOLO
import cv2

# Load the trained YOLO model
model = YOLO('runs/detect/train/weights/best.pt') 

# Open the camera (0 for default camera, 1 for external camera)
cap = cv2.VideoCapture(1)

# Check if the camera opened successfully
if not cap.isOpened():
    print("Error: Cannot open camera.")
    exit()

# Create a window
cv2.namedWindow("YOLO Realtime Detection", cv2.WINDOW_NORMAL)

# Main loop: read frames from the camera and perform detection
while True:
    ret, frame = cap.read()
    if not ret:
        print("Failed to grab frame.")
        break

    # Perform detection using YOLO
    results = model.predict(source=frame, conf=0.25, verbose=False)

    # Get the annotated visualization frame
    annotated_frame = results[0].plot()

    # Display the annotated frame
    cv2.imshow("YOLO Realtime Detection", annotated_frame)

    # Press 'q' to exit
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Release resources
cap.release()
cv2.destroyAllWindows()
