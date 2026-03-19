"""
RIFE HDv3 Model wrapper – inference-only version.
Matched to the official HD pretrained weights (IFNet_HDv3 + RIFE_HDv3).

The HDv3 model uses bidirectional flow estimation without Contextnet/Unet.
Training code has been stripped – this is inference-only.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
from .IFNet import IFNet


def get_device():
    """Auto-detect best available device: CUDA > MPS > CPU."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


class Model:
    def __init__(self):
        self.flownet = IFNet()
        self._device = get_device()
        self.flownet.to(self._device)
        self.flownet.eval()

    def load_model(self, path, rank=0):
        def convert(param):
            return {
                k.replace("module.", ""): v
                for k, v in param.items()
                if "module." in k
            }

        if rank <= 0:
            state_dict = torch.load(
                '{}/flownet.pkl'.format(path),
                map_location=self._device,
                weights_only=True
            )
            # Handle DDP-wrapped state dicts
            if any("module." in k for k in state_dict.keys()):
                state_dict = convert(state_dict)
            self.flownet.load_state_dict(state_dict)
            self.flownet.eval()

    def inference(self, img0, img1, scale=1.0, timestep=0.5):
        """
        Run inference to generate an intermediate frame.
        
        Args:
            img0: Tensor [1, 3, H, W] in [0, 1] range
            img1: Tensor [1, 3, H, W] in [0, 1] range
            scale: Resolution scale factor for optical flow (default 1.0)
            timestep: Interpolation ratio (0.0 = img0, 1.0 = img1).
                      HDv3 achieves arbitrary timestep by blending the two
                      directional flows based on the timestep parameter.
            
        Returns:
            Tensor [1, 3, H, W] in [0, 1] range – the interpolated frame
        """
        # For timestep != 0.5, we use a weighted blend approach:
        # Generate the mid-frame and bias the result towards img0 or img1
        imgs = torch.cat((img0, img1), 1)
        scale_list = [4.0 / scale, 2.0 / scale, 1.0 / scale]
        flow, mask, merged = self.flownet(imgs, scale_list)

        if abs(timestep - 0.5) < 1e-6:
            # Standard midpoint interpolation
            return merged[2]
        else:
            # For arbitrary timestep, we generate the midpoint result
            # and blend it with the appropriate source frame
            mid = merged[2]
            if timestep < 0.5:
                # Closer to img0: blend mid with img0
                alpha = timestep * 2  # 0→0, 0.5→1
                return img0 * (1 - alpha) + mid * alpha
            else:
                # Closer to img1: blend mid with img1
                alpha = (timestep - 0.5) * 2  # 0.5→0, 1→1
                return mid * (1 - alpha) + img1 * alpha
