"""One CPU interpreter owned exclusively by the hub's inference thread."""
import hashlib
import io
from pathlib import Path

import numpy as np
from PIL import Image
from ai_edge_litert.interpreter import Interpreter

MODEL_SHA256 = '2e04c53bfeac0ac2a30c057c7e2a777594ce39baaac35a92f74fb1e8c4fc4e0b'
VEHICLE_LABELS = {2: 'car', 3: 'motorcycle', 5: 'bus', 7: 'truck'}


class PersonDetector:
    def __init__(self, model, threads=2):
        if hashlib.sha256(Path(model).read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError('Detector model checksum does not match')
        self.interpreter = Interpreter(model_path=str(model), num_threads=threads)
        self.interpreter.allocate_tensors()
        self.input = self.interpreter.get_input_details()[0]
        self.outputs = self.interpreter.get_output_details()
        if list(self.input['shape']) != [1, 320, 320, 3] or self.input['dtype'] != np.uint8:
            raise ValueError('Unexpected detector input')

    def detect(self, jpeg):
        """Retain the person-only API used by earlier validation tools."""
        return self.detect_objects(jpeg)['people']

    def detect_objects(self, jpeg):
        """Read people and road vehicles from one unchanged model invocation."""
        with Image.open(io.BytesIO(jpeg)) as image:
            if image.width * image.height > 4_000_000:
                raise ValueError('Camera image is too large for detection')
            rgb = image.convert('RGB').resize((320, 320), Image.Resampling.BILINEAR)
            tensor = np.asarray(rgb, dtype=np.uint8)[None, ...]
        self.interpreter.set_tensor(self.input['index'], tensor)
        self.interpreter.invoke()
        boxes, classes, scores, count = [self.interpreter.get_tensor(item['index']) for item in self.outputs]
        people, vehicles = [], []
        for box, cls, score in zip(boxes[0][:int(count[0])], classes[0], scores[0]):
            category = int(cls)
            if (category != 0 and category not in VEHICLE_LABELS) or score < .3:
                continue
            top, left, bottom, right = (max(0., min(1., float(value))) for value in box)
            if right > left and bottom > top:
                item = {'bbox': [left, top, right-left, bottom-top], 'score': float(score)}
                if category == 0:
                    people.append(item)
                else:
                    vehicles.append({**item, 'label': VEHICLE_LABELS[category]})
        return {'people': people, 'vehicles': vehicles}
