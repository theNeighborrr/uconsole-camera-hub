EfficientDet Lite0 object detection model, downloaded from TensorFlow's official Raspberry Pi example model URL:
https://storage.googleapis.com/download.tensorflow.org/models/tflite/task_library/object_detection/rpi/lite-model_efficientdet_lite0_detection_metadata_1.tflite

Example: https://github.com/tensorflow/examples/tree/master/lite/examples/object_detection/raspberry_pi

SHA256: 2e04c53bfeac0ac2a30c057c7e2a777594ce39baaac35a92f74fb1e8c4fc4e0b

Input: uint8 RGB, 320x320. Outputs: normalized yxyx boxes, zero-based COCO label indices, scores, count. The model's embedded labelmap.txt identifies index 0 as person. The current server retains people and car, truck, bus, and motorcycle results from the same inference pass at scores of at least 0.30; each viewer applies its own display threshold (default 0.50). The exact model checksum is checked. No police classifier is included.

The LiteRT Interpreter runs on the CM4 CPU using two threads. Inference uses no accelerator or cloud service. The model and runtime are installed locally; inference does not require internet. Individual video sources such as Ring still need internet to supply footage.
