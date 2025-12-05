import pyrealsense2 as rs
import numpy as np
import cv2
import serial
import time
import glob

# ==========================================================
# Configuration Parameters
# ==========================================================
# Frame freeze threshold: how many consecutive identical frames =
# considered "camera frozen"
FREEZE_MAX_FRAMES = 60   # About 2 seconds (~30 FPS)

# ----------------------------------------------------------
# Serial Port
# ----------------------------------------------------------
ser = serial.Serial('/dev/ttyTHS1', 115200, timeout=1)
time.sleep(2)
print("✅ Serial connected: /dev/ttyTHS1, baudrate 115200")

# ----------------------------------------------------------
# Initialize RealSense
# ----------------------------------------------------------
pipeline = rs.pipeline()
config = rs.config()
config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
profile = pipeline.start(config)

align_to = rs.stream.color
align = rs.align(align_to)

# ----------------------------------------------------------
# USB Camera Auto Scan + Auto Reconnect Function
# ----------------------------------------------------------
def open_usb_cam(cam_label, preferred_index=None, width=640, height=480):
    """
    Automatically open USB camera.
    Steps:
        1. Try preferred_index if provided
        2. If failed, scan /dev/video* and open the first available one
    cam_label is only for log printing ("A" or "B")
    """
    tried = []

    print(f"\n🔁 [{cam_label}] Trying to open camera...")

    # -------------------------------
    # 1. Try user-specified index first
    # -------------------------------
    if preferred_index is not None:
        cam = cv2.VideoCapture(preferred_index)
        tried.append(f"index {preferred_index}")
        if cam.isOpened():
            cam.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cam.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            print(f"🎯 [{cam_label}] Successfully opened camera with index {preferred_index}")
            return cam
        else:
            cam.release()
            print(f"⚠️ [{cam_label}] Failed to open index {preferred_index}, scanning /dev/video* ...")

    # -------------------------------
    # 2. Scan /dev/video*
    # -------------------------------
    video_nodes = sorted(glob.glob("/dev/video*"))
    print(f"🔍 [{cam_label}] Found video devices: {video_nodes}")

    for dev in video_nodes:
        try:
            cam = cv2.VideoCapture(dev)
            tried.append(dev)
            if cam.isOpened():
                cam.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cam.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                print(f"✅ [{cam_label}] Successfully opened camera: {dev}")
                return cam
            else:
                cam.release()
        except Exception as e:
            print(f"⚠️ [{cam_label}] Failed to open {dev}: {e}")
            continue

    print(f"❌ [{cam_label}] Camera open failed, tried: {tried}")
    return None

# Preferred indexes (not stable, but used as first candidates)
cam_A_index = 6
cam_B_index = 8

cam_A = open_usb_cam("A", cam_A_index)
cam_B = open_usb_cam("B", cam_B_index)

# Cache last frame & freeze counter
last_frameA = None
last_frameB = None
freeze_count_A = 0
freeze_count_B = 0

# ----------------------------------------------------------
# ArUco Parameters
# ----------------------------------------------------------
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)
aruco_params = cv2.aruco.DetectorParameters()
detector = cv2.aruco.ArucoDetector(aruco_dict, aruco_params)

# ----------------------------------------------------------
# ArUco Drawing Function
# ----------------------------------------------------------
def mark_aruco(frame, corners, ids, color=(0,255,0), show_depth=False, depth_frame=None, intrin=None):
    h, w = frame.shape[:2]
    cx0 = w // 2
    cy0 = h // 2

    for i, pts in enumerate(corners):
        pts = pts[0].astype(int)
        cx = int((pts[0][0] + pts[2][0]) / 2)
        cy = int((pts[0][1] + pts[2][1]) / 2)

        cv2.polylines(frame, [pts], True, color, 2)
        cv2.circle(frame, (cx, cy), 6, (0,0,255), -1)
        cv2.putText(frame, f"ID {ids[i][0]}", (pts[0][0], pts[0][1] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        x_dir = cx - cx0
        y_dir = cy0 - cy

        if show_depth and depth_frame is not None and intrin is not None:
            depth = depth_frame.get_distance(cx, cy)
            if depth > 0:
                X, Y, Z = rs.rs2_deproject_pixel_to_point(intrin, [cx, cy], depth)
            else:
                Z = 0.0
            cv2.putText(frame, f"({x_dir},{y_dir},{Z:.2f}m)", (cx + 10, cy + 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 2)
        else:
            cv2.putText(frame, f"({x_dir},{y_dir})", (cx + 10, cy + 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
    return frame


# ----------------------------------------------------------
# Main Loop
# ----------------------------------------------------------
try:
    while True:

        # ============================================================
        # STEP 1 : RealSense
        # ============================================================
        frames = pipeline.wait_for_frames()
        aligned = align.process(frames)

        depth_frame = aligned.get_depth_frame()
        color_frame = aligned.get_color_frame()
        if not depth_frame or not color_frame:
            print("⚠️ RealSense failed to get frame, skipping this loop")
            continue

        intrin = depth_frame.profile.as_video_stream_profile().intrinsics
        color_img = np.asanyarray(color_frame.get_data())
        gray_rs = cv2.cvtColor(color_img, cv2.COLOR_BGR2GRAY)

        corners_rs, ids_rs, _ = detector.detectMarkers(gray_rs)
        rs_detected = (ids_rs is not None)

        rs_show = color_img.copy()
        chosen = None

        if rs_detected:
            chosen = "RealSense"
            rs_show = mark_aruco(
                rs_show, corners_rs, ids_rs,
                color=(0,255,0),
                show_depth=True,
                depth_frame=depth_frame,
                intrin=intrin
            )

        cv2.putText(rs_show, f"Chosen: {chosen}", (20,40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,255), 2)


        # ============================================================
        # STEP 2 : WebCam A (dropout & freeze detection + auto reconnect)
        # ============================================================
        A_detected = False
        frameA = None

        if cam_A is not None:
            retA, frameA = cam_A.read()

            # 1) Failed to read -> reconnect
            if not retA or frameA is None:
                print("❌ [A] Read failed, camera considered disconnected, rescanning!")
                cam_A.release()
                cam_A = open_usb_cam("A", cam_A_index)
                last_frameA = None
                freeze_count_A = 0
            else:
                # 2) Detect freeze: same as last frame
                if last_frameA is not None:
                    if np.array_equal(frameA, last_frameA):
                        freeze_count_A += 1
                    else:
                        freeze_count_A = 0
                last_frameA = frameA.copy()

                if freeze_count_A >= FREEZE_MAX_FRAMES:
                    print("❌ [A] Frame frozen continuously, rescanning!")
                    cam_A.release()
                    cam_A = open_usb_cam("A", cam_A_index)
                    last_frameA = None
                    freeze_count_A = 0
                    frameA = None
                else:
                    grayA = cv2.cvtColor(frameA, cv2.COLOR_BGR2GRAY)
                    cornersA, idsA, _ = detector.detectMarkers(grayA)
                    A_detected = (idsA is not None)
                    if A_detected:
                        frameA = mark_aruco(frameA, cornersA, idsA)
                    cv2.putText(frameA, "WebCam A", (10,30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
        else:
            cam_A = open_usb_cam("A", cam_A_index)
            last_frameA = None
            freeze_count_A = 0


        # ============================================================
        # STEP 3 : WebCam B (dropout & freeze detection + auto reconnect)
        # ============================================================
        B_detected = False
        frameB = None

        if cam_B is not None:
            retB, frameB = cam_B.read()

            if not retB or frameB is None:
                print("❌ [B] Read failed, camera considered disconnected, rescanning!")
                cam_B.release()
                cam_B = open_usb_cam("B", cam_B_index)
                last_frameB = None
                freeze_count_B = 0
            else:
                if last_frameB is not None:
                    if np.array_equal(frameB, last_frameB):
                        freeze_count_B += 1
                    else:
                        freeze_count_B = 0
                last_frameB = frameB.copy()

                if freeze_count_B >= FREEZE_MAX_FRAMES:
                    print("❌ [B] Frame frozen continuously, rescanning!")
                    cam_B.release()
                    cam_B = open_usb_cam("B", cam_B_index)
                    last_frameB = None
                    freeze_count_B = 0
                    frameB = None
                else:
                    grayB = cv2.cvtColor(frameB, cv2.COLOR_BGR2GRAY)
                    cornersB, idsB, _ = detector.detectMarkers(grayB)
                    B_detected = (idsB is not None)
                    if B_detected:
                        frameB = mark_aruco(frameB, cornersB, idsB, color=(255,0,0))
                    cv2.putText(frameB, "WebCam B", (10,30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,255), 2)
        else:
            cam_B = open_usb_cam("B", cam_B_index)
            last_frameB = None
            freeze_count_B = 0


        # ============================================================
        # STEP 4 — Send Serial Data (RealSense has highest priority)
        # ============================================================
        if rs_detected:
            pts = corners_rs[0][0].astype(int)
            cx = int((pts[0][0] + pts[2][0]) / 2)
            cy = int((pts[0][1] + pts[2][1]) / 2)
            cx0 = color_img.shape[1] // 2
            cy0 = color_img.shape[0] // 2

            x_dir = cx - cx0
            y_dir = cy0 - cy
            Z = depth_frame.get_distance(cx, cy)

            data_str = f"{x_dir:.3f},{Z:.3f}\n"
            chosen = "RealSense"

        elif A_detected:
            data_str = "255.000,0.600\n"
            chosen = "WebCam_A"

        elif B_detected:
            data_str = "-255.000,0.600\n"
            chosen = "WebCam_B"

        else:
            data_str = "0.000,0.000\n"
            chosen = "None"

        ser.write(data_str.encode("utf-8"))
        print(f"📤 Source={chosen} → {data_str.strip()}")


        # ============================================================
        # STEP 5 — Display
        # ============================================================
        cv2.imshow("RealSense", rs_show)
        if frameA is not None:
            cv2.imshow("WebCam_A", frameA)
        if frameB is not None:
            cv2.imshow("WebCam_B", frameB)

        if cv2.waitKey(1) == 27:  # ESC to exit
            break

finally:
    print("🔧 Releasing resources …")
    pipeline.stop()
    if cam_A is not None:
        cam_A.release()
    if cam_B is not None:
        cam_B.release()
    ser.close()
    cv2.destroyAllWindows()
    print("✅ Program exited.")

