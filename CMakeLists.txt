cmake_minimum_required(VERSION 3.13.4)

project(RoTMS)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://www.slicer.org/wiki/Documentation/Nightly/Extensions/RoTMS")
set(EXTENSION_CATEGORY "RoTMS")
set(EXTENSION_CONTRIBUTORS "Yihao Liu (Johns Hopkins University), Jiaming Zhang (Johns Hopkins University)")
set(EXTENSION_DESCRIPTION "This is an extension for Robotic-TMS.")
set(EXTENSION_ICONURL "http://www.example.com/Slicer/Extensions/RoTMS.png")
set(EXTENSION_SCREENSHOTURLS "http://www.example.com/Slicer/Extensions/RoTMS/Screenshots/1.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies

#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
add_subdirectory(RobotControl)
add_subdirectory(MedImgPlan)
add_subdirectory(TargetVisualization)
add_subdirectory(SlicerTestExample)
add_subdirectory(Simulation)
## NEXT_MODULE

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})

