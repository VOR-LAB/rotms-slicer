"""
MIT License

Copyright (c) 2022 Yihao Liu, Johns Hopkins University

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import os
import json
import logging

import vtk
import qt
import ctk
import slicer
from slicer.ScriptedLoadableModule import *
from slicer.util import VTKObservationMixin

from TargetVisualizationLib.UtilConnections import UtilConnections
from TargetVisualizationLib.UtilSlicerFuncs import setTransform
from TargetVisualizationLib.UtilSlicerFuncs import setColorByDistance
from TargetVisualizationLib.UtilConnectionsWtNnBlcRcv import UtilConnectionsWtNnBlcRcv
from TargetVisualizationLib.UtilCalculations import quat2mat

#
# TargetVisualization
#


class TargetVisualization(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Target Visualization"
        self.parent.categories = ["RoTMS"]
        # TODO: add here list of module names that this module requires
        self.parent.dependencies = []
        self.parent.contributors = ["Yihao Liu (Johns Hopkins University)"]
        # TODO: update with short description of the module and a link to online module documentation
        self.parent.helpText = """
This is an example of scripted loadable module bundled in an extension.
See more information in <a href="https:">module documentation</a>.
"""
        # TODO: replace with organization, grant and thanks
        self.parent.acknowledgementText = """
This file was originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""

        # Additional initialization step after application startup is complete
        slicer.app.connect("startupCompleted()", appStartUpPostAction)


def appStartUpPostAction():
    return

#
# TargetVisualizationWidget
#


class TargetVisualizationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.__init__(self, parent)
        # needed for parameter node observation
        VTKObservationMixin.__init__(self)
        self.logic = None
        self._parameterNode = None
        self._updatingGUIFromParameterNode = False

    def setup(self):
        """
        Called when the user opens the module the first time and the widget is initialized.
        """
        ScriptedLoadableModuleWidget.setup(self)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(
            self.resourcePath('UI/TargetVisualization.ui'))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = TargetVisualizationLogic(self.resourcePath('Configs/'))

        # Connections

        # These connections ensure that we update parameter node when scene is closed
        self.addObserver(
            slicer.mrmlScene, slicer.mrmlScene.StartCloseEvent, self.onSceneStartClose)
        self.addObserver(slicer.mrmlScene,
                         slicer.mrmlScene.EndCloseEvent, self.onSceneEndClose)

        # These connections ensure that whenever user changes some settings on the GUI, that is saved in the MRML scene
        # (in the selected parameter node).
        # self.ui.selectorModel.connect("currentNodeChanged(vtkMRMLNode*)", self.updateParameterNodeFromGUI)
        self.ui.sliderColorThresh.connect(
            "valueChanged(double)", self.updateParameterNodeFromGUI)

        # Buttons
        self.ui.pushModuleRobCtrl.connect(
            'clicked(bool)', self.onPushModuleRobCtrl)
        self.ui.pushModuleMedImgPlan.connect(
            'clicked(bool)', self.onPushModuleMedImgPlan)

        self.ui.pushStartTargetViz.connect(
            'clicked(bool)', self.onPushStartTargetViz)
        self.ui.pushStopTargetViz.connect(
            'clicked(bool)', self.onPushStopTargetViz)

        self.ui.pushSavePlanAndRealPose.connect(
            'clicked(bool)', self.onPushSavePlanAndRealPose)
        self.ui.pushSaveContinuousPose.connect(
            'clicked(bool)', self.onPushSaveContinuousPose)

        # Make sure parameter node is initialized (needed for module reload)
        self.initializeParameterNode()

    def cleanup(self):
        """
        Called when the application closes and the module widget is destroyed.
        """
        self.removeObservers()
        self.logic._connections.clear()

    def enter(self):
        """
        Called each time the user opens this module.
        """
        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self):
        """
        Called each time the user opens a different module.
        """
        # Do not react to parameter node changes (GUI wlil be updated when the user enters into the module)
        self.removeObserver(
            self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

    def onSceneStartClose(self, caller, event):
        """
        Called just before the scene is closed.
        """
        # Parameter node will be reset, do not use it anymore
        self.setParameterNode(None)

    def onSceneEndClose(self, caller, event):
        """
        Called just after the scene is closed.
        """
        # If this module is shown while the scene is closed then recreate a new parameter node immediately
        if self.parent.isEntered:
            self.initializeParameterNode()

    def initializeParameterNode(self):
        """
        Ensure parameter node exists and observed.
        """
        # Parameter node stores all user choices in parameter values, node selections, etc.
        # so that when the scene is saved and reloaded, these settings are restored.

        self.setParameterNode(self.logic.getParameterNode())

    def setParameterNode(self, inputParameterNode):
        """
        Set and observe parameter node.
        Observation is needed because when the parameter node is changed then the GUI must be updated immediately.
        """

        if inputParameterNode:
            self.logic.setDefaultParameters(inputParameterNode)

        # Unobserve previously selected parameter node and add an observer to the newly selected.
        # Changes of parameter node are observed so that whenever parameters are changed by a script or any other module
        # those are reflected immediately in the GUI.
        if self._parameterNode is not None:
            self.removeObserver(
                self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)
        self._parameterNode = inputParameterNode
        if self._parameterNode is not None:
            self.addObserver(
                self._parameterNode, vtk.vtkCommand.ModifiedEvent, self.updateGUIFromParameterNode)

        # Initial GUI update
        self.updateGUIFromParameterNode()

    def updateGUIFromParameterNode(self, caller=None, event=None):
        """
        This method is called whenever parameter node is changed.
        The module GUI is updated to show the current state of the parameter node.
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        # Make sure GUI changes do not call updateParameterNodeFromGUI (it could cause infinite loop)
        self._updatingGUIFromParameterNode = True

        # Update node selectors and sliders
        self.ui.sliderColorThresh.value = float(
            self._parameterNode.GetParameter("ColorChangeThresh"))

        # Update buttons states and tooltips
        if self._parameterNode.GetParameter("Visualizing") == "true":
            self.ui.pushStartTargetViz.toolTip = "The module is visualizing"
            self.ui.pushStartTargetViz.enabled = False
            self.ui.pushStopTargetViz.toolTip = "Stop visualizing"
            self.ui.pushStopTargetViz.enabled = True
            self.ui.pushSavePlanAndRealPose.toolTip = "Save data"
            self.ui.pushSavePlanAndRealPose.enabled = True
        else:
            self.ui.pushStartTargetViz.toolTip = "Start visualizing"
            self.ui.pushStartTargetViz.enabled = True
            self.ui.pushStopTargetViz.toolTip = "Visualization not started"
            self.ui.pushStopTargetViz.enabled = False
            self.ui.pushSavePlanAndRealPose.toolTip = "Start visualization first"
            self.ui.pushSavePlanAndRealPose.enabled = False

        # All the GUI updates are done
        self._updatingGUIFromParameterNode = False

    def updateParameterNodeFromGUI(self, caller=None, event=None):
        """
        This method is called when the user makes any change in the GUI.
        The changes are saved into the parameter node (so that they are restored when the scene is saved and loaded).
        """

        if self._parameterNode is None or self._updatingGUIFromParameterNode:
            return

        # Modify all properties in a single batch
        wasModified = self._parameterNode.StartModify()

        self._parameterNode.SetParameter(
            "ColorChangeThresh", str(self.ui.sliderColorThresh.value))

        self._parameterNode.EndModify(wasModified)

    def onPushModuleRobCtrl(self):
        slicer.util.selectModule("RobotControl")

    def onPushModuleMedImgPlan(self):
        slicer.util.selectModule("MedImgPlan")

    def onPushStartTargetViz(self):
        msg = self.logic._commandsData["VISUALIZE_START"]
        try:
            self.logic._connections.utilSendCommand(msg)
        except:
            return
        self.logic.processStartTargetViz()
        self._parameterNode.SetParameter("Visualizing", "true")

    def onPushStopTargetViz(self):
        msg = self.logic._commandsData["VISUALIZE_STOP"]
        try:
            self.logic._connections.utilSendCommand(msg)
        except:
            return
        self.logic.processStopTargetViz()
        self._parameterNode.SetParameter("Visualizing", "false")

    def onPushSavePlanAndRealPose(self):
        msg = self.logic._commandsData["VISUALIZE_SAVE_PLANANDREAL_POSE"]
        try:
            self.logic._connections.utilSendCommand(msg)
        except:
            return
    
    def onPushSaveContinuousPose(self):
        msg = self.logic._commandsData["VISUALIZE_SAVE_CONTINUOUS_POSE"]
        try:
            self.logic._connections.utilSendCommand(msg)
        except:
            return


#
# TargetVisualizationLogic
#

class TargetVisualizationLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, configPath):
        """
        Called when the logic class is instantiated. Can be used for initializing member variables.
        """
        ScriptedLoadableModuleLogic.__init__(self)
        self._configPath = configPath
        self._connections = TargetVizConnections(configPath, "TARGETVIZ")
        self._connections.setup()
        self._parameterNode = self.getParameterNode()

        with open(self._configPath+"CommandsConfig.json") as f:
            self._commandsData = (json.load(f))["TargetVizCmd"]

    def setDefaultParameters(self, parameterNode):
        """
        Initialize parameter node with default settings.
        """
        if not parameterNode.GetParameter("ColorChangeThresh"):
            parameterNode.SetParameter("ColorChangeThresh", "20.0")
        if not parameterNode.GetParameter("Visualizing"):
            parameterNode.SetParameter("Visualizing", "false")

    def processStartTargetViz(self):
        """
        Called when click the start target viz button
        """
        self._parameterNode = self.getParameterNode()
        self._connections._parameterNode = self.getParameterNode()

        if not self._parameterNode.GetNodeReference("CurrentPoseTransform"):
            transformNode = slicer.vtkMRMLTransformNode()
            slicer.mrmlScene.AddNode(transformNode)
            self._parameterNode.SetNodeReferenceID(
                "CurrentPoseTransform", transformNode.GetID())

        if not self._parameterNode.GetNodeReference("CurrentPoseIndicator"):
            with open(self._configPath+"Config.json") as f:
                configData = json.load(f)
            inputModel = slicer.util.loadModel(
                self._configPath+configData["POSE_INDICATOR_MODEL"])
            self._parameterNode.SetNodeReferenceID(
                "CurrentPoseIndicator", inputModel.GetID())

        currentPoseTransform = self._parameterNode.GetNodeReference(
            "CurrentPoseTransform")
        currentPoseIndicator = self._parameterNode.GetNodeReference(
            "CurrentPoseIndicator")
        currentPoseTransform.SetMatrixTransformToParent(
            self._connections._transformMatrixCurrentPose)
        currentPoseIndicator.SetAndObserveTransformNodeID(
            currentPoseTransform.GetID())

        if not self._connections._transformNodeTargetPoseSingleton:
            if slicer.mrmlScene.GetSingletonNode("MedImgPlan.TargetPoseTransform", "vtkMRMLTransformNode"):
                self._connections._transformNodeTargetPoseSingleton = \
                    slicer.mrmlScene.GetSingletonNode(
                        "MedImgPlan.TargetPoseTransform", "vtkMRMLTransformNode")

        self._connections._currentPoseIndicator = currentPoseIndicator
        self._connections._colorchangethresh = float(
            self._parameterNode.GetParameter("ColorChangeThresh"))

        self._connections._flag_receiving_nnblc = True
        self._connections.receiveTimerCallBack()

    def processStopTargetViz(self):

        self._connections._flag_receiving_nnblc = False

#
# Use UtilConnectionsWtNnBlcRcv and override the data handler
#


class TargetVizConnections(UtilConnectionsWtNnBlcRcv):

    def __init__(self, configPath, modulesufx):
        super().__init__(configPath, modulesufx)
        self._transformMatrixCurrentPose = None
        self._transformNodeTargetPoseSingleton = None
        self._currentPoseIndicator = None

    def setup(self):
        super().setup()
        if not self._transformMatrixCurrentPose:
            self._transformMatrixCurrentPose = vtk.vtkMatrix4x4()

    def handleReceivedData(self):
        """
        Override the parent class function
        """
        mat, p = self.utilMsgParse()
        self.utilPoseMsgCallback(mat, p)

    def utilMsgParse(self):
        """
        Msg format: "__msg_pose_0000.00000_0000.00000_0000.00000_0000.00000_0000.00000_0000.00000_0000.00000"
            x, y, z, qx, qy, qz, qw
            in mm
        """
        data = self._data_buff.decode("UTF-8")
        msg = data[11:]
        num_str = msg.split("_")
        num = []
        for i in num_str:
            num.append(float(i))
        p = num[0:3]
        mat = quat2mat(num[3:])
        return mat, p

    def utilPoseMsgCallback(self, mat, p):
        """
        Called each time when a valid pose message is received
        """

        setTransform(mat, p, self._transformMatrixCurrentPose)
        self._parameterNode.GetNodeReference(
            "CurrentPoseTransform").SetMatrixTransformToParent(self._transformMatrixCurrentPose)

        if self._transformNodeTargetPoseSingleton:

            targetTransform = \
                self._transformNodeTargetPoseSingleton.GetMatrixTransformToParent()
            setColorByDistance(
                self._currentPoseIndicator, targetTransform, self._transformMatrixCurrentPose, self._colorchangethresh)

        slicer.app.processEvents()
