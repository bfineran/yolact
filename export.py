# Copyright (c) 2021 - present / Neuralmagic, Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Helper script to export yolact models to ONNX

##########
Command help:
usage: export.py [-h] --checkpoint CHECKPOINT [--config CONFIG] \
    [--recipe RECIPE] [--convert-qat] [--batch-size BATCH_SIZE] \
    [--image-shape IMAGE_SHAPE [IMAGE_SHAPE ...]] \
    [--save-dir SAVE_DIR] [--name NAME]

Export yolact models to ONNX

optional arguments:
  -h, --help            show this help message and exit
  --checkpoint CHECKPOINT
                        The yolact pytorch checkpoint to export
  --config CONFIG, -c CONFIG
                        The config used to train the yolact model,
                        for ex: yolact_darknet53_config, yolact_resnet50_config,
                        etc...; Defaults to yolact_base_config.
  --recipe RECIPE, -r RECIPE
                        Path or SparseZoo stub to the recipe used for training,
                        omit if no recipe used.
  --convert-qat, -Q     Flag to convert a QAT(Quantization Aware Training) graph
  --batch-size BATCH_SIZE, -b BATCH_SIZE
                        The batch size to use while exporting the Model graph to
                        ONNX;Defaults to 1
  --image-shape IMAGE_SHAPE [IMAGE_SHAPE ...], -S IMAGE_SHAPE [IMAGE_SHAPE ...]
                        The image shape in (C, S, S) format to use for exporting
                        the Model graph to ONNX; Defaults to (3, 550, 550)
  --save-dir SAVE_DIR, -s SAVE_DIR
                        The directory to save exported models to; Defaults to
                        "./exported_models"
  --name NAME, -n NAME  The name to use for saving the exported ONNX model

##########
Example usage:
python export.py --checkpoint ./checkpoints/yolact_darknet53_ks.pth \
    --recipe ./recipes/yolact_ks.yaml \
    --config yolact_darknet53_config

##########
Example Two:
python export.py --checkpoint ./quantized-checkpoint/yolact_darknet53_1_10.pth \
    --recipe ./recipes/yolact.quant.yaml \
    --save-dir ./exported-models \
    --name yolact_darknet53_quantized \
    --batch-size 1 \
    --image-shape 3 550 550 \
    --config yolact_darknet53_config
"""

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import torch

from data import set_cfg
from yolact import Yolact
from sparseml.pytorch.optim import ScheduledModifierManager
from sparseml.pytorch.utils import export_onnx


logging.basicConfig(level=logging.INFO)


@dataclass
class ExportArgs:
    """
    Typed arguments for exporting a yolact model to ONNX
    """

    checkpoint: Path
    config: str
    recipe: str
    no_qat: bool
    batch_size: int
    image_shape: Iterable
    save_dir: Path
    name: Path

    def __post_init__(self):
        """
        post-initialization processing and validation
        """
        self.checkpoint = Path(self.checkpoint)

        if not self.checkpoint.exists():
            raise FileNotFoundError(
                f"The checkpoint {self.checkpoint} does " f"not exist."
            )

        self.image_shape = tuple(self.image_shape)
        self.save_dir = Path(self.save_dir)
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.name = self.get_safe_name()

    def get_safe_name(self):
        if self.name:
            self.name = Path(self.name)
        else:
            self.name = Path(self.checkpoint.with_suffix(".onnx").name)

        filename = self.name.stem
        self.name = self.save_dir / f"{filename}.onnx"
        existence_counter = 0
        while self.name.exists():
            existence_counter += 1
            self.name = self.name.parent / f"{filename}-{existence_counter}.onnx"
        return self.name


def parse_args() -> ExportArgs:
    """
    Add and parse arguments for exporting a yolact model to ONNX

    :return: A ExportArgs Object with typed arguments
    """
    parser = argparse.ArgumentParser(description="Export yolact models to ONNX")

    parser.add_argument(
        "--checkpoint",
        type=str,
        required=True,
        help="The yolact pytorch checkpoint to export",
    )

    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default="yolact_base_config",
        help="The config used to train the yolact model, for ex: "
        "yolact_darknet53_config, yolact_resnet50_config, etc...; "
        "Defaults to yolact_base_config.",
    )

    parser.add_argument(
        "--recipe",
        "-r",
        type=str,
        default=None,
        help="Path or SparseZoo stub to the recipe used for training, "
        "omit if no recipe used.",
    )

    parser.add_argument(
        "--no-qat",
        "-N",
        action="store_true",
        help="Flag to prevent conversion of a QAT(Quantization Aware Training) "
             "Graph to a Quantized Graph",
    )

    parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=1,
        help="The batch size to use while exporting the Model graph to ONNX;"
        "Defaults to 1",
    )

    parser.add_argument(
        "--image-shape",
        "-S",
        type=int,
        nargs="+",
        default=(3, 550, 550),
        help="The image shape in (C, S, S) format to use for exporting the "
        "Model graph to ONNX; Defaults to (3, 550, 550)",
    )

    parser.add_argument(
        "--save-dir",
        "-s",
        type=str,
        default="./exported_models",
        help="The directory to save exported models to; "
        'Defaults to "./exported_models"',
    )

    parser.add_argument(
        "--name",
        "-n",
        type=str,
        default=None,
        help="The name to use for saving the exported ONNX model",
    )

    args = parser.parse_args()
    return ExportArgs(**vars(args))


def export(args: ExportArgs):
    batch_shape = (args.batch_size, *args.image_shape)
    set_cfg(args.config)
    model = Yolact()

    if args.recipe is not None:
        manager = ScheduledModifierManager.from_yaml(file_path=args.recipe)
        manager.apply(model)

    logging.debug(f"Loading state dict from checkpoint {args.checkpoint}")
    model.load_state_dict(torch.load(args.checkpoint))
    export_onnx(
        module=model,
        sample_batch=torch.randn(*batch_shape),
        file_path=str(args.name),
        convert_qat=not args.no_qat,
    )
    logging.info(f"Model checkpoint exported to {args.name}")


if __name__ == "__main__":
    export_args = parse_args()
    export(export_args)
