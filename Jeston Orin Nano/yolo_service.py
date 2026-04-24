import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import String
from cv_bridge import CvBridge
import cv2
from ultralytics import YOLO
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy

class JetsonYoloFinal(Node):
    def __init__(self):
        super().__init__('jetson_yolo_final')

        # QoS Profile for Zero Latency
        qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1
        )

        self.input_topic = '/ascamera/camera_publisher/rgb0/image'
        self.output_topic = '/jetson/yolo_annotated'
        self.label_topic = '/yolo_label'

        self.model = YOLO('yolov8n.pt')
        self.bridge = CvBridge()

        # Subscription with optimized QoS
        self.sub = self.create_subscription(Image, self.input_topic, self.cb, qos)

        # Publishers
        self.pub = self.create_publisher(Image, self.output_topic, qos)
        self.label_pub = self.create_publisher(String, self.label_topic, 10)

        self.get_logger().info('Node Started - Zero Latency Mode Active')

    def cb(self, msg):
        try:
            raw_frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')

            # Inference with performance optimizations
            results = self.model.predict(raw_frame, conf=0.15, imgsz=320, verbose=False)

            if len(results[0].boxes) > 0:
                class_id = int(results[0].boxes[0].cls[0])
                label_name = self.model.names[class_id]

                label_msg = String()
                label_msg.data = label_name
                self.label_pub.publish(label_msg)
                self.get_logger().info(f'Detected: {label_name}')

                # Visual output
                annotated = results[0].plot()
                out_msg = self.bridge.cv2_to_imgmsg(annotated, encoding='bgr8')
                out_msg.header = msg.header
                self.pub.publish(out_msg)

        except Exception as e:
            self.get_logger().error(f'Error: {str(e)}')

def main(args=None):
    rclpy.init(args=args)
    node = JetsonYoloFinal()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
