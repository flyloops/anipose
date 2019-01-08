"""
DeepLabCut Toolbox
https://github.com/AlexEMG/DeepLabCut

A Mathis, alexander.mathis@bethgelab.org
M Mathis, mackenzie@post.harvard.edu
P Karashchuk, pierrek@uw.edu

This script analyzes videos based on a trained network.
You need tensorflow for evaluation. Run by:
CUDA_VISIBLE_DEVICES=0 python3 AnalyzeVideos.py

"""

####################################################
# Dependencies
####################################################

import os.path
import sys

## TODO: use deeplabcut v2 instead of this
# pose_path = '/home/pierre/research/tuthill/DeepLabCut_pierre/pose-tensorflow'
pose_path = '/home/tuthill/pierre/DeepLabCut_pierre/pose-tensorflow'

sys.path.append(pose_path)

# subfolder = os.getcwd().split('pipeline')[0]
# sys.path.append(subfolder)
# add parent directory: (where nnet & config are!)
# sys.path.append(subfolder + "pose-tensorflow/")
# sys.path.append(subfolder + "Generating_a_Training_Set")

# from myconfig_pipeline import cropping, Task, date, \
#     trainingsFraction, resnet, trainingsiterations, snapshotindex, shuffle,x1, x2, y1, y2
# from myconfig_pipeline import pipeline_prefix, pipeline_videos_raw, pipeline_pose

# Deeper-cut dependencies
from config import load_config
from nnet import predict
from dataset.pose_dataset import data_to_input

# Dependencies for video:
import pickle
# import matplotlib.pyplot as plt
# import imageio
# imageio.plugins.ffmpeg.download()
import skimage.color
import time
import pandas as pd
import numpy as np
import os
from tqdm import tqdm
from glob import glob
import warnings
import cv2

def getpose(image, net_cfg, outputs, outall=False):
    ''' Adapted from DeeperCut, see pose-tensorflow folder'''
    image_batch = data_to_input(skimage.color.gray2rgb(image))
    outputs_np = sess.run(outputs, feed_dict={inputs: image_batch})
    scmap, locref = predict.extract_cnn_output(outputs_np, net_cfg)
    pose = predict.argmax_pose_predict(scmap, locref, net_cfg.stride)
    if outall:
        return scmap, locref, pose
    else:
        return pose


##################################################
# Datafolder
##################################################

def process_video(vidname, dataname, net_stuff):
    sess, inputs, outputs, net_cfg = net_stuff
    
    # clip = VideoFileClip(vidname)
    cap = cv2.VideoCapture(vidname)
    nframes = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    start = time.time()
    PredicteData = np.zeros((nframes, 3 * len(net_cfg['all_joints_names'])))

    # print("Starting to extract posture")
    for index in tqdm(range(nframes), ncols=70):
        ret, frame = cap.read()
        if not ret:
            break
        try:
            image = cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
        except:
            break
        # image = img_as_ubyte(clip.get_frame(index * 1. / fps))
        pose = getpose(image, net_cfg, outputs)
        PredicteData[index, :] = pose.flatten()
        # NOTE: thereby net_cfg['all_joints_names'] should be same order as bodyparts!

    cap.release()
    stop = time.time()

    dictionary = {
        "start": start,
        "stop": stop,
        "run_duration": stop - start,
        "Scorer": scorer,
        "config file": net_cfg,
        "fps": fps,
        "frame_dimensions": (height, width),
        "nframes": nframes
    }
    metadata = {'data': dictionary}

    pdindex = pd.MultiIndex.from_product(
        [net_cfg['all_joints_names'], ['x', 'y', 'likelihood']],
        names=['bodyparts', 'coords'])

    # print("Saving results...")
    DataMachine = pd.DataFrame(
        PredicteData, columns=pdindex, index=range(nframes))
    DataMachine.to_hdf(
        dataname, 'df_with_missing', format='table', mode='w')
    with open(os.path.splitext(dataname)[0] + '_metadata.pickle',
              'wb') as f:
        pickle.dump(metadata, f, pickle.HIGHEST_PROTOCOL)

def get_folders(path):
    folders = next(os.walk(path))[1]
    return sorted(folders)

def process_session(config, session_path, net_stuff):
    pipeline_videos_raw = config['pipeline_videos_raw']
    pipeline_calibration = config['pipeline_calibration']
    pipeline_pose = config['pipeline_pose_2d']

    ## TODO: process all videos here, except those with calibration prefix
    videos = glob(os.path.join(session_path, pipeline_videos_raw, 'vid'+'*.avi'))
    videos = sorted(videos)

    for video in videos:
        basename = os.path.basename(video)
        basename, _ = os.path.splitext(basename)
        os.makedirs(os.path.join(session_path, pipeline_pose), exist_ok=True)
        dataname_base = basename + '.h5'
        dataname = os.path.join(session_path, pipeline_pose, dataname_base)
        print(dataname)
        try:
            # Attempt to load data...
            pd.read_hdf(dataname)
            # print("Video already analyzed!", dataname)
        except:
            # print("Loading ", video)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                # print('reprocess', video)
                process_video(video, dataname, net_stuff)
    


def pose_videos_all(config):
    pipeline_prefix = config['path']

    model_path = os.path.join(config['model_folder'], config['model_name'])
    
    net_cfg = load_config(os.path.join(model_path, 'test', "pose_cfg.yaml"))

    net_cfg['init_weights'] = os.path.join(model_path, 'train',
                                           'snapshot-{}'.format(
                                               config['model_train_iter']))

    scorer = 'DeepCut_{}_{}'.format(config['model_name'], config['model_train_iter'])
    sess, inputs, outputs = predict.setup_pose_prediction(net_cfg)

    net_stuff = sess, inputs, outputs, net_cfg
    
    sessions = get_folders(pipeline_prefix)
    
    for session in sessions:
        print(session)
        session_path = os.path.join(pipeline_prefix, session)

        process_session(config, session_path, net_stuff)
        