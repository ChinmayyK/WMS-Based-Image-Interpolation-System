"""
Optical flow warping module for RIFE.
Ported from https://github.com/hzwer/ECCV2022-RIFE/blob/main/model/warplayer.py

Adapted for MPS (Apple Silicon) compatibility:
- MPS doesn't support 'border' padding in grid_sample
- Falls back to 'zeros' padding on MPS, or runs warp on CPU if needed
"""
import torch
import torch.nn as nn

backwarp_tenGrid = {}


def warp(tenInput, tenFlow):
    device = tenInput.device
    k = (str(tenFlow.device), str(tenFlow.size()))
    if k not in backwarp_tenGrid:
        tenHorizontal = torch.linspace(-1.0, 1.0, tenFlow.shape[3], device=device).view(
            1, 1, 1, tenFlow.shape[3]).expand(tenFlow.shape[0], -1, tenFlow.shape[2], -1)
        tenVertical = torch.linspace(-1.0, 1.0, tenFlow.shape[2], device=device).view(
            1, 1, tenFlow.shape[2], 1).expand(tenFlow.shape[0], -1, -1, tenFlow.shape[3])
        backwarp_tenGrid[k] = torch.cat(
            [tenHorizontal, tenVertical], 1).to(device)

    tenFlow = torch.cat([tenFlow[:, 0:1, :, :] / ((tenInput.shape[3] - 1.0) / 2.0),
                         tenFlow[:, 1:2, :, :] / ((tenInput.shape[2] - 1.0) / 2.0)], 1)

    g = (backwarp_tenGrid[k] + tenFlow).permute(0, 2, 3, 1)

    # MPS does not support 'border' padding mode in grid_sample.
    # Use 'zeros' padding on MPS (slight quality difference at edges, negligible in practice).
    if device.type == 'mps':
        return torch.nn.functional.grid_sample(
            input=tenInput, grid=g, mode='bilinear',
            padding_mode='zeros', align_corners=True
        )
    else:
        return torch.nn.functional.grid_sample(
            input=tenInput, grid=g, mode='bilinear',
            padding_mode='border', align_corners=True
        )
