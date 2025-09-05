# SmartCam Project

An awesome project that does amazing things!

---

## Background

This project is based on the YOLOv8 algorithm. We trained a set of models specifically for detecting road traffic elements such as vehicles, traffic lights, pedestrians, and traffic signs. These models lay the groundwork for enabling object detection capabilities in smart camera modules for autonomous driving systems.

---

## Method

The data training process is divided into four main steps:

### Step 1: Download the Dataset

This project uses datasets from [Roboflow](https://roboflow.com/).

1. Visit [https://roboflow.com/](https://roboflow.com/).
2. Sign in with an existing account or sign up for a new one.
3. Click "Universe" in the left sidebar, or go directly to [https://universe.roboflow.com/](https://universe.roboflow.com/).  
   > ⚠️ Note: You must be logged in to download datasets.
4. Choose a dataset and click **"Download Project"**.
5. Then click **"Download Dataset"**.
6. Select **YOLOv8** as the export format and choose **"Download ZIP to Computer"**.
7. After downloading, extract the compressed dataset locally.

---

### Step 2: Set Up `data.yaml`

Open the file `MODEL_TRAIN.py` and configure the following:

- **Dataset path:** Set the `"data"` field to the full path of your `data.yaml` file.  
- **Device:** Set `device = 0` to use GPU (set `device = 'cpu'` if no GPU is available).  
- **Epochs:** We use 50 epochs for training.

---

### Step 3: Train the Model

Make sure you have all required dependencies installed. Then run your training script `MODEL_TRAIN.py`

---

### Step 4: 

Once the .pt file is ready, you can use it in different application scenarios:

- Image demonstration
- Video denonstration
- Real-time demonstration(camera-based)

---

## Reports
As of May 5th, 2025, this project includes 2 reports:
- Mid-term Report - 2025 Spring Semester
- Final-term Report - 2025 Spring Semester
