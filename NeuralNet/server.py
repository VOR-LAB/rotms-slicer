"""
============================
Tracked TMS nifti image data server
Receive dA/dt field from 3DSlicer, predict the E-field and send data back to 3DSlicer
============================
"""

import pyigtl  # pylint: disable=import-error
import os
import sys
import asyncio
os.environ['KMP_DUPLICATE_LIB_OK']='True'
import numpy as np
import nibabel as nib
import torch
from collections import OrderedDict
from model import Modified3DUNet
from numpy import linalg as LA
import time

# Make pyigtl text decoding tolerant of unexpected encodings so we can always
# receive dataset paths sent from Slicer.
from pyigtl.messages import MessageBase  # noqa: E402

def _safe_decode_text(encoded_text, encoding):  # noqa: E302
    try:
        if encoding == MessageBase.IANA_CHARACTER_SET_ASCII:
            return encoded_text.decode('ascii')
        if encoding == MessageBase.IANA_CHARACTER_SET_UTF8:
            return encoded_text.decode('utf8')
        return encoded_text.decode('utf8', errors='ignore')
    except Exception as exc:  # pylint: disable=broad-exception-caught
        print(f"Failed to decode text message: {exc}")
        return ""

MessageBase.decode_text = staticmethod(_safe_decode_text)



class ServerTMS():
    def __init__(self, dataset_path=None):
        self.dataset_path = dataset_path
        self.cond_data = None
        self.xyz = None
        self.device = None
        self.net = None
        self.stop_server = False

    async def run_server(self):
        servertms = pyigtl.OpenIGTLinkServer(port=18944, local_server=True)
        text_server = pyigtl.OpenIGTLinkServer(port=18945, local_server=True)

        if self.dataset_path:
            self.configure_dataset(self.dataset_path)

        while not self.stop_server:
            self._process_text_messages(text_server)

            if self.net is None or self.cond_data is None:
                await asyncio.sleep(0.01)
                continue

            if not servertms.is_connected():
                await asyncio.sleep(0.01)
                continue

            messages = servertms.get_latest_messages()
            for message in messages:
                if not hasattr(message, "image"):
                    continue
                outputData = self._predict(message.image)
                image_message = pyigtl.ImageMessage(outputData, device_name="pyigtl_data")
                servertms.send_message(image_message)

            await asyncio.sleep(0)

    async def stop(self):
        self.stop_server = True

    def _process_text_messages(self, text_server):
        if not text_server.is_connected():
            return
        messages = text_server.get_latest_messages()
        for message in messages:
            dataset = getattr(message, "string", None) or getattr(message, "data", None)
            if not dataset:
                continue
            dataset = dataset.strip()
            self.configure_dataset(dataset)

    def configure_dataset(self, dataset_path):
        try:
            resolved_path = self._resolve_dataset_path(dataset_path)
        except FileNotFoundError as exc:
            print(exc)
            return

        if resolved_path == self.dataset_path and self.net is not None and self.cond_data is not None:
            return

        print(f"Selected dataset: {resolved_path}\nWaiting for 3DSlicer connection...")
        self.dataset_path = resolved_path

        try:
            self._load_static_data()
            self._load_model()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"Failed to load dataset at {resolved_path}: {exc}")
            self.net = None
            self.cond_data = None
            self.xyz = None

    def _load_static_data(self):
        cond_path = os.path.join(self.dataset_path, 'conductivity.nii.gz')
        cond = nib.load(cond_path)
        cond_data = cond.get_fdata()
        self.xyz = cond_data.shape
        self.cond_data = np.reshape(cond_data, ([self.xyz[0], self.xyz[1], self.xyz[2], 1]))
        print('Image shape:', self.cond_data.shape)

    def _load_model(self):
        model_path = os.path.join(self.dataset_path, 'model.pth.tar')

        in_channels = 4
        out_channels = 3
        base_n_filter = 16

        use_cuda = torch.cuda.is_available()
        print('Cuda available: ', use_cuda)

        self.device = torch.device('cuda' if use_cuda else 'cpu')
        print('Using device:', self.device)

        net = Modified3DUNet(in_channels, out_channels, base_n_filter)
        net = net.float()
        if use_cuda:
            checkpoint = torch.load(model_path, map_location='cuda:0')
        else:
            checkpoint = torch.load(model_path, map_location='cpu')

        new_state_dict = OrderedDict()
        for k, v in checkpoint['model_state_dict'].items():
            name = k[7:] if k.startswith('module.') else k
            new_state_dict[name] = v
        net.load_state_dict(new_state_dict)
        if use_cuda:
            net = net.cuda()

        self.net = net

    def _predict(self, magvec):
        magvec = np.transpose(magvec, axes=(2, 1, 0, 3))
        mask = np.concatenate((self.cond_data, self.cond_data, self.cond_data), axis=3)
        magvec = (mask > 0) * magvec
        inputData = np.concatenate((self.cond_data, magvec * 1000000), axis=3)

        inputData = inputData.transpose(3, 0, 1, 2)
        size = np.array([1, 4,  self.xyz[0], self.xyz[1], self.xyz[2]])
        inputData = np.reshape(inputData, size)
        inputData = np.double(inputData)

        st = time.time()
        inputData_gpu = torch.from_numpy(inputData).to(self.device)
        outputData = self.net(inputData_gpu.float())
        outputData = outputData.cpu()
        outputData = outputData.detach().numpy()
        outputData = outputData.transpose(2, 3, 4, 1, 0)
        outputData = np.reshape(outputData, ([self.xyz[0], self.xyz[1], self.xyz[2], 3]))
        outputData = np.transpose(outputData, axes=(2, 1, 0, 3))
        outputData = LA.norm(outputData, axis = 3)

        et = time.time()
        elapsed_time = et - st
        print(elapsed_time)
        return outputData

    @staticmethod
    def _resolve_dataset_path(dataset_path):
        if not dataset_path:
            raise FileNotFoundError("Dataset path not provided. Send a valid directory from 3DSlicer.")
        candidate = dataset_path
        if not os.path.isabs(candidate):
            script_path = os.path.dirname(os.path.abspath(__file__))
            candidate = os.path.abspath(os.path.join(script_path, '..', dataset_path))
        if not os.path.isdir(candidate):
            raise FileNotFoundError(f"Dataset directory does not exist: {candidate}")
        return candidate

async def main():
    initial_dataset = sys.argv[1] if len(sys.argv) > 1 else None
    tmsserver = ServerTMS(initial_dataset)
    await tmsserver.run_server()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server interrupted by user. Stopping...")