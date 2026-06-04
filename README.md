# RoTMS - Robotic TMS Extension for 3D Slicer

This extension enables planning and visualization for Robotic Transcranial Magnetic Stimulation (RoTMS) procedures in 3D Slicer.

![plan](https://github.com/bingogome/rotms-slicer/blob/main/preopplan.png)

## Overview

The RoTMS Slicer extension consists of three main modules:

1. **MedImgPlan**: Medical image planning for TMS target selection
   - Plan TMS stimulation targets on brain or skin models
   - Calculate and visualize registration errors 
   - Create grid-based stimulation plans
   - Visualize MEP (Motor Evoked Potentials) responses as heatmaps on the cortex

2. **RobotControl**: Control interface for the TMS robot
   - Connect to robot systems
   - Execute planned motions
   - Manual adjustment of robot positions
   - Monitoring robot state

3. **TargetVisualization**: Real-time visualization of target and actual tool positions
   - Visualize planned vs. actual positions
   - Capture and save pose data

## Installation

### Prerequisites
- 3D Slicer (version 4.11 or newer) - [Download here](https://download.slicer.org/)
- Python package: PyYAML

### Installing PyYAML in 3D Slicer
Before installing RoTMS, you must install the PyYAML package in 3D Slicer:

1. Open 3D Slicer
2. Go to Python Interactor (View → Python Interactor)
3. Enter the following command:
   ```python
   pip_install('PyYAML')
   ```
4. Wait for the installation to complete

### Installing RoTMS Extension
There are two ways to install the RoTMS extension:

#### Option 1: Using the Extension Manager (Recommended for end users)
1. Open 3D Slicer
2. Go to View → Extension Manager
3. Click on "Install Extensions" tab
4. Search for "RoTMS"
5. Click Install
6. Restart 3D Slicer when prompted

#### Option 2: Manual Installation (For developers)
1. Clone the repository:
   ```
   git clone https://github.com/bingogome/rotms-slicer.git
   ```
2. Open 3D Slicer
3. Go to Edit → Application Settings
4. Select "Modules" category
5. In "Additional module paths", add the path to the cloned repository
6. Click "Apply" and restart 3D Slicer

## Configuration

### Network Configuration
The extension components communicate using UDP sockets. You can modify the connection settings in the configuration files:

- MedImgPlan: `MedImgPlan/Resources/Configs/Config.json`
- RobotControl: `RobotControl/Resources/Configs/Config.json`
- TargetVisualization: `TargetVisualization/Resources/Configs/Config.json`

### Command Configuration
Commands sent between components are defined in the following files:

- MedImgPlan: `MedImgPlan/Resources/Configs/CommandsConfig.json`
- RobotControl: `RobotControl/Resources/Configs/CommandsConfig.json`
- TargetVisualization: `TargetVisualization/Resources/Configs/CommandsConfig.json`

## Usage

1. Start by loading your anatomical models (skin, brain) in the MedImgPlan module
2. Plan TMS targets on the brain or skin models
3. Use TargetVisualization to verify target positions
4. Control the robot using the RobotControl module

For detailed instructions on each module, refer to the documentation or tooltips in the application.

## License

This software is released under the MIT License. See the LICENSE file for details.

## Acknowledgements

@article{liu2025image, title={An Image-Guided Robotic System for Transcranial Magnetic Stimulation: System Development and Experimental Evaluation}, author={Liu, Yihao and Zhang, Jiaming and Ai, Letian and Tian, Jing and Sefati, Shahriar and Liu, Huan and Martin-Gomez, Alejandro and Kheradmand, Amir and Armand, Mehran}, journal={IEEE Robotics and Automation Letters}, year={2025}, publisher={IEEE} }
