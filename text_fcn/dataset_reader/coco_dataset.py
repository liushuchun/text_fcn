# coding=utf-8
from __future__ import absolute_import
from __future__ import division

import os

import cv2
import numpy as np

from text_fcn import coco_utils
from text_fcn.dataset_reader.dataset_reader import BatchDataset


class CocoDataset(BatchDataset):

    def __init__(self,
                 coco_ids,
                 ct,
                 coco_dir,
                 batch_size,
                 image_size,
                 crop=False,
                 pre_saved=False):
        """
        :param coco_ids:
        :param ct: COCO_Text object instance
        :param coco_dir: directory to coco dataset
        :param batch_size:
        :param image_size: crop window size if pre_saved=False
                           image size if pre_saved=True (0 if variable)
        :param crop: whether to crop images to image_size
        :param pre_saved: whether to read images from storage or generate them on the go

        Here's some examples
            - pre_saved = True
                - batch_size = 1, image_size = 0, crop = False
                    Load images from storage and do not crop them.
                - batch_size = X, image_size = Y, crop = False
                    Load images from storage which are asserted to have the same size = image_size.
                - batch_size = X, image_size = Y, crop = True
                    Load images from storage and crop them to image_size.
            - pre_saved = False
                - batch_size = 1, image_size = 0, crop = False
                    Generate images and do not crop them.
                - batch_size = X, image_size = Y, crop = False
                    Generate images which are asserted to have the same size = image_size.
                - batch_size = X, image_size = Y, crop = True
                    Generate images and crop them to image_size.
        """
        # crop only when crop_size if given AND images are not loaded from disk
        crop_fun = self._crop_resize if crop else None
        BatchDataset.__init__(self, coco_ids, batch_size, image_size, image_op=crop_fun)

        self.ct = ct
        self.coco_dir = coco_dir
        self.pre_saved = pre_saved

        if self.pre_saved:
            self._get_image = self._load_image
        else:
            self._get_image = self._gen_image

    def _gen_image(self, coco_id):
        """
        Generate images using self.ct data
        :param coco_id: image's coco id
        :return: image, its groundtruth w/o illegibles and its weights
        """
        fname = self.ct.imgs[coco_id]['file_name'][:-3] + 'png'
        image = cv2.imread(
            os.path.join(self.coco_dir, 'images/', fname)
        )
        ann_fst = np.zeros(image.shape[:-1], dtype=np.uint8)
        ann_snd = np.zeros(image.shape[:-1], dtype=np.uint8)
        weight = np.ones(ann_fst.shape, np.float32)

        for ann in self.ct.imgToAnns[coco_id]:
            poly = np.array(self.ct.anns[ann]['polygon'], np.int32).reshape((4,2))
            if self.ct.anns[ann]['legibility'] == 'legible':
                # draw only legible bbox/polygon
                cv2.fillConvexPoly(ann_fst, poly, 255)
            else:
                # 0 weight if it is illegible
                cv2.fillConvexPoly(weight, poly, 0.0)

        for ann in self.ct.imgToAnns[coco_id]:
            poly = np.array(self.ct.anns[ann]['polygon'], np.int32)
            bbox = np.array(self.ct.anns[ann]['bbox'], np.int32)

            if self.ct.anns[ann]['legibility'] == 'legible':
                # thickness = minimum between 10% height and width
                thick = int(max(2, np.min(bbox[2:] * 0.1)))
                cv2.drawContours(ann_snd, poly.reshape((1,4,1,2)), -1, 255, thickness=thick)

        return [image, np.dstack((ann_fst, ann_snd)), weight]

    def _load_image(self, coco_id):
        """
        Load image already saved on the disk
        """
        fname = 'COCO_train2014_%012d.png' % coco_id
        image = cv2.imread(
            os.path.join(self.coco_dir, 'images/', fname))
        annotation = cv2.imread(
            os.path.join(self.coco_dir, 'anns/', fname))
        annotation = cv2.cvtColor(annotation, cv2.COLOR_BGR2GRAY)
        weight = cv2.imread(
            os.path.join(self.coco_dir, 'weights/', fname))
        weight = cv2.cvtColor(weight, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.

        return [image, annotation, weight]

    def _crop_resize(self, image, annotation, weight, name=None):
        # next level hacks
        assert name is not None
        valid_anns = [
            ann for ann in self.ct.imgToAnns[name]
            if self.ct.anns[ann]['legibility'] == 'legible'
        ]
        ann = np.random.choice(valid_anns)
        # extract bbox => x, y, w, h
        bbox_rect = np.int32(self.ct.anns[ann]['bbox'])
        window = coco_utils.get_window(annotation.shape[:2], bbox_rect)
        return coco_utils.crop_resize([image, annotation, weight], window, self.image_size)
