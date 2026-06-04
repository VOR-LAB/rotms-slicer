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
import math

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


BULLSEYE_LAYOUT_ID = 5001
BULLSEYE_LAYOUT_XML = """
<layout type="horizontal" split="true">
  <item splitSize="700">
    <view class="vtkMRMLViewNode" singletontag="1">
      <property name="viewlabel" action="default">1</property>
    </view>
  </item>
  <item splitSize="300">
    <view class="vtkMRMLViewNode" singletontag="Bullseye">
      <property name="viewlabel" action="default">B</property>
    </view>
  </item>
</layout>
"""


class BullseyeCanvasWidget(qt.QWidget):

    def __init__(self, configPath, parent=None):
        super().__init__(parent)
        with open(configPath + "Config.json") as f:
            configData = json.load(f)
        self._pixTarget = qt.QPixmap(configPath + configData.get("BULLSEYE_MARKER_TARGET", ""))
        self._pixCurrent = qt.QPixmap(configPath + configData.get("BULLSEYE_MARKER_CURRENT", ""))
        self._pixPointer = qt.QPixmap(configPath + configData.get("ORIENTATION_POINTER", ""))

        self._relX = 0.0
        self._relY = 0.0
        self._relZ = 0.0
        self._pointerAngle = 0.0
        self._pointerProjLen = 0.0
        self._zRotation = 0.0

        palette = self.palette
        palette.setColor(qt.QPalette.Window, qt.QColor(255, 255, 255))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

    def updateFromRelativeTransform(self, relX, relY, relZ, pointerAngle, pointerProjLen, zRotation):
        self._relX = relX
        self._relY = relY
        self._relZ = relZ
        self._pointerAngle = pointerAngle
        self._pointerProjLen = pointerProjLen
        self._zRotation = zRotation
        self.update()

    def paintEvent(self, event):
        painter = qt.QPainter(self)
        painter.setRenderHint(qt.QPainter.Antialiasing, True)

        canvasSize = min(self.width, self.height)
        offsetX = (self.width - canvasSize) / 2.0
        offsetY = (self.height - canvasSize) / 2.0
        center = canvasSize / 2.0

        imgW = self._pixTarget.width() if self._pixTarget.width() > 0 else 1000
        imgH = self._pixTarget.height() if self._pixTarget.height() > 0 else 1000
        imgScale = canvasSize / float(imgW)
        mmToPx = canvasSize / 50.0

        painter.save()
        painter.translate(offsetX, offsetY)

        # Layer 1: target bullseye (static, centered)
        painter.save()
        painter.scale(imgScale, imgScale)
        painter.drawPixmap(0, 0, self._pixTarget)
        painter.restore()

        # Layer 2: orientation pointer (centered, rotated + height-scaled)
        if self._pointerProjLen > 1e-6:
            painter.save()
            painter.translate(center, center)
            painter.rotate(math.degrees(self._pointerAngle))
            ptrW = self._pixPointer.width() if self._pixPointer.width() > 0 else 1000
            ptrH = self._pixPointer.height() if self._pixPointer.height() > 0 else 1000
            ptrScale = canvasSize / float(ptrW)
            painter.scale(ptrScale, ptrScale * self._pointerProjLen)
            painter.drawPixmap(int(-ptrW / 2), int(-ptrH / 2), self._pixPointer)
            painter.restore()

        # Layer 3: current bullseye (translated by relX/relY, rotated by zRotation, scaled by exp(-|relZ|))
        painter.save()
        txPx = center - self._relX * mmToPx
        tyPx = center + self._relY * mmToPx
        zScale = math.exp(-abs(self._relZ / 1000.0))
        painter.translate(txPx, tyPx)
        painter.rotate(-math.degrees(self._zRotation))
        curW = self._pixCurrent.width() if self._pixCurrent.width() > 0 else 1000
        curH = self._pixCurrent.height() if self._pixCurrent.height() > 0 else 1000
        curScale = imgScale * zScale
        painter.scale(curScale, curScale)
        painter.drawPixmap(int(-curW / 2), int(-curH / 2), self._pixCurrent)
        painter.restore()

        painter.restore()
        painter.end()

    def resizeEvent(self, event):
        self.update()


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
        self._previousLayoutId = None
        self._bullseyeCanvas = None
        self._bullseyeThreeDWidget = None

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
        self.ui.comboMeshSelectorCoil.connect(
            "currentIndexChanged(int)", self.updateParameterNodeFromGUI)
        for name in self.logic._coilModelFiles.keys():
            self.ui.comboMeshSelectorCoil.addItem(name)

        # Buttons
        self.ui.pushModuleRobCtrl.connect(
            'clicked(bool)', self.onPushModuleRobCtrl)
        self.ui.pushModuleMedImgPlan.connect(
            'clicked(bool)', self.onPushModuleMedImgPlan)
        self.ui.pushModuleSimulation.connect(
            'clicked(bool)', self.onPushModuleSimulation)

        self.ui.pushStartTargetViz.connect(
            'clicked(bool)', self.onPushStartTargetViz)
        self.ui.pushStopTargetViz.connect(
            'clicked(bool)', self.onPushStopTargetViz)

        self.ui.pushSavePlanAndRealPose.connect(
            'clicked(bool)', self.onPushSavePlanAndRealPose)
        self.ui.pushSaveContinuousPose.connect(
            'clicked(bool)', self.onPushSaveContinuousPose)

        # Register the bullseye layout
        layoutManager = slicer.app.layoutManager()
        layoutManager.layoutLogic().GetLayoutNode().AddLayoutDescription(
            BULLSEYE_LAYOUT_ID, BULLSEYE_LAYOUT_XML)

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
        layoutManager = slicer.app.layoutManager()
        self._previousLayoutId = layoutManager.layout
        layoutManager.setLayout(BULLSEYE_LAYOUT_ID)

        for i in range(layoutManager.threeDViewCount):
            widget = layoutManager.threeDWidget(i)
            if widget.mrmlViewNode().GetSingletonTag() == "Bullseye":
                self._bullseyeThreeDWidget = widget
                widget.threeDView().hide()
                widget.threeDController().hide()
                self._bullseyeCanvas = BullseyeCanvasWidget(
                    self.logic._configPath, widget)
                widget.layout().addWidget(self._bullseyeCanvas)
                break

        # Make sure parameter node exists and observed
        self.initializeParameterNode()

    def exit(self):
        """
        Called each time the user opens a different module.
        """
        if self._bullseyeCanvas and self._bullseyeThreeDWidget:
            self._bullseyeCanvas.setParent(None)
            self._bullseyeCanvas.deleteLater()
            self._bullseyeCanvas = None
            self._bullseyeThreeDWidget.threeDView().show()
            self._bullseyeThreeDWidget.threeDController().show()
            self._bullseyeThreeDWidget = None

        if self._previousLayoutId is not None:
            slicer.app.layoutManager().setLayout(self._previousLayoutId)
            self._previousLayoutId = None

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
        coilName = self._parameterNode.GetParameter("CoilModelName")
        if coilName:
            idx = self.ui.comboMeshSelectorCoil.findText(coilName)
            if idx >= 0:
                self.ui.comboMeshSelectorCoil.setCurrentIndex(idx)
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
        self._parameterNode.SetParameter(
            "CoilModelName", self.ui.comboMeshSelectorCoil.currentText)

        self._parameterNode.EndModify(wasModified)

    def onPushModuleRobCtrl(self):
        slicer.util.selectModule("RobotControl")

    def onPushModuleMedImgPlan(self):
        slicer.util.selectModule("MedImgPlan")

    def onPushModuleSimulation(self):
        slicer.util.selectModule("Simulation")

    def onPushStartTargetViz(self):
        msg = self.logic._commandsData["VISUALIZE_START"]
        try:
            self.logic._connections.utilSendCommand(msg)
        except:
            return
        self.logic.processStartTargetViz()
        self._parameterNode.SetParameter("Visualizing", "true")
        self._startBullseyeUpdates()

    def _startBullseyeUpdates(self):
        currentTransformNode = self._parameterNode.GetNodeReference("CurrentPoseTransform")
        if currentTransformNode:
            self.addObserver(currentTransformNode,
                             slicer.vtkMRMLTransformNode.TransformModifiedEvent,
                             self._updateBullseyeCanvas)
            self._updateBullseyeCanvas()

    def _stopBullseyeUpdates(self):
        currentTransformNode = self._parameterNode.GetNodeReference("CurrentPoseTransform")
        if currentTransformNode:
            self.removeObserver(currentTransformNode,
                                slicer.vtkMRMLTransformNode.TransformModifiedEvent,
                                self._updateBullseyeCanvas)

    def _updateBullseyeCanvas(self, caller=None, event=None):
        if not self._bullseyeCanvas:
            return
        targetTransformNode = self.logic._connections._transformNodeTargetPoseSingleton
        currentTransformNode = self._parameterNode.GetNodeReference("CurrentPoseTransform")
        if not targetTransformNode or not currentTransformNode:
            return

        matTarget = targetTransformNode.GetMatrixTransformToParent()
        matCurrent = currentTransformNode.GetMatrixTransformToParent()

        targetInv = vtk.vtkMatrix4x4()
        vtk.vtkMatrix4x4.Invert(matTarget, targetInv)
        rel = vtk.vtkMatrix4x4()
        vtk.vtkMatrix4x4.Multiply4x4(targetInv, matCurrent, rel)

        relX = rel.GetElement(0, 3)
        relY = rel.GetElement(1, 3)
        relZ = rel.GetElement(2, 3)

        r00, r01, r02 = rel.GetElement(0,0), rel.GetElement(0,1), rel.GetElement(0,2)
        r10, r11, r12 = rel.GetElement(1,0), rel.GetElement(1,1), rel.GetElement(1,2)
        r20, r21, r22 = rel.GetElement(2,0), rel.GetElement(2,1), rel.GetElement(2,2)

        trace = r00 + r11 + r22
        cosTheta = max(-1.0, min(1.0, (trace - 1.0) / 2.0))
        theta = math.acos(cosTheta)
        sinTheta = math.sin(theta)

        pointerAngle = 0.0
        pointerProjLen = 0.0

        if abs(sinTheta) > 1e-6:
            kx = (r21 - r12) / (2.0 * sinTheta)
            ky = (r02 - r20) / (2.0 * sinTheta)
            pointerProjLen = math.sqrt(kx * kx + ky * ky)
            pointerAngle = math.atan2(ky, kx)

        zRotation = math.atan2(r10, r00)

        self._bullseyeCanvas.updateFromRelativeTransform(
            relX, relY, relZ, pointerAngle, pointerProjLen, zRotation)

    def onPushStopTargetViz(self):
        msg = self.logic._commandsData["VISUALIZE_STOP"]
        try:
            self.logic._connections.utilSendCommand(msg)
        except:
            return
        self._stopBullseyeUpdates()
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

        with open(self._configPath + "Config.json") as f:
            configData = json.load(f)
        self._coilModelFiles = configData.get("POSE_INDICATOR_MODELS", {})
        self._coilModelNodes = {}

    def _getCoilModelNode(self, name):
        if name in self._coilModelNodes:
            return self._coilModelNodes[name]
        filename = self._coilModelFiles.get(name)
        if not filename:
            return None
        filepath = self._configPath + filename
        if not os.path.exists(filepath):
            return None
        node = slicer.util.loadModel(filepath)
        node.SetName("coil_" + name)
        node.GetDisplayNode().SetVisibility(False)
        self._coilModelNodes[name] = node
        return node

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

        coilName = self._parameterNode.GetParameter("CoilModelName")
        coilModelNode = self._getCoilModelNode(coilName) if coilName else None
        currentIndicator = self._parameterNode.GetNodeReference("CurrentPoseIndicator")

        if coilModelNode and currentIndicator and currentIndicator.GetID() != coilModelNode.GetID():
            currentIndicator.GetDisplayNode().SetVisibility(False)
            currentIndicator = None
            self._parameterNode.SetNodeReferenceID("CurrentPoseIndicator", None)

        if not currentIndicator:
            if coilModelNode:
                inputModel = coilModelNode
            else:
                with open(self._configPath+"Config.json") as f:
                    configData = json.load(f)
                inputModel = slicer.util.loadModel(
                    self._configPath+configData["POSE_INDICATOR_MODEL"])
            if inputModel:
                inputModel.GetDisplayNode().SetVisibility(True)
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
