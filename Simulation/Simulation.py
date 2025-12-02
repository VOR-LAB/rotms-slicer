import os
import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
import sys
import Loader as L


class Simulation(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = "Simulation"
        self.parent.categories = ["RoTMS"]
        self.parent.dependencies = []
        self.parent.contributors = ["Jiaming Zhang (Johns Hopkins University)"]
        self.parent.helpText = """
This module provides TMS visualization and control functionality.
"""
        self.parent.acknowledgementText = """
This work was supported by your funding source.
"""
        self.parent = parent

    # def setup(self):
    #     ScriptedLoadableModule.setup(self)

    # def cleanup(self):
    #     ScriptedLoadableModule.cleanup(self)

class SimulationWidget(ScriptedLoadableModuleWidget):
    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        self.guiMessages = True
        self.consoleMessages = True
        self.showGMButton = None
        self.loader = None
        self.example_path = self._defaultExamplePath()
        self.selectedCoilMode = "Free Pose"
        self.parameterNode = None

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)

        self._setupTextConnector()
        self._ensureParameterNode()
        self.setupButtons()
        self.layout.addStretch(1)

    def setupButtons(self):
        self.collapsibleButton = ctk.ctkCollapsibleButton()
        self.collapsibleButton.text = "TMS Visualization"
        self.layout.addWidget(self.collapsibleButton)
        self.formLayout = qt.QFormLayout(self.collapsibleButton)

        # Data directory selection
        self.examplePathEdit = qt.QLineEdit(self.collapsibleButton)
        self.examplePathEdit.text = self.example_path
        browseButton = qt.QPushButton("Browse", self.collapsibleButton)
        pathLayout = qt.QHBoxLayout()
        pathLayout.addWidget(self.examplePathEdit)
        pathLayout.addWidget(browseButton)
        pathWidget = qt.QWidget(self.collapsibleButton)
        pathWidget.setLayout(pathLayout)
        self.formLayout.addRow("Data directory", pathWidget)
        browseButton.clicked.connect(self._onBrowseDataDirectory)

        # Coil placement mode
        self.coilModeCombo = qt.QComboBox(self.collapsibleButton)
        self.coilModeCombo.addItems(["Free Pose", "Planned Pose"])
        self.coilModeCombo.currentTextChanged.connect(self.onCoilModeChanged)
        self.formLayout.addRow("Coil placement", self.coilModeCombo)
        
        slicer.modules.tractographydisplay.widgetRepresentation().activateWindow()
        self.loadExampleButton = qt.QPushButton("Load Example", self.collapsibleButton)
        self.formLayout.addRow(self.loadExampleButton)
        self.loadExampleButton.clicked.connect(self.onLoadExampleClicked)

        assetOverridesBox = qt.QGroupBox("Asset overrides", self.collapsibleButton)
        assetLayout = qt.QFormLayout(assetOverridesBox)
        self.formLayout.addRow(assetOverridesBox)

        self.coilSelector = slicer.qMRMLNodeComboBox(assetOverridesBox)
        self.coilSelector.nodeTypes = ["vtkMRMLModelNode"]
        self.coilSelector.noneEnabled = True
        self.coilSelector.addEnabled = False
        self.coilSelector.removeEnabled = False
        self.coilSelector.renameEnabled = False
        self.coilSelector.showHidden = False
        self.coilSelector.setMRMLScene(slicer.mrmlScene)
        assetLayout.addRow("Coil model", self.coilSelector)
        self.coilSelector.currentNodeChanged.connect(lambda node: self._updateParameterNodeReference('coilModelNodeID', node))

        self.skinSelector = slicer.qMRMLNodeComboBox(assetOverridesBox)
        self.skinSelector.nodeTypes = ["vtkMRMLModelNode"]
        self.skinSelector.noneEnabled = True
        self.skinSelector.addEnabled = False
        self.skinSelector.removeEnabled = False
        self.skinSelector.renameEnabled = False
        self.skinSelector.showHidden = False
        self.skinSelector.setMRMLScene(slicer.mrmlScene)
        assetLayout.addRow("Skin model", self.skinSelector)
        self.skinSelector.currentNodeChanged.connect(lambda node: self._updateParameterNodeReference('skinModelNodeID', node))

        self.magnormSelector = slicer.qMRMLNodeComboBox(assetOverridesBox)
        self.magnormSelector.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        self.magnormSelector.noneEnabled = True
        self.magnormSelector.addEnabled = False
        self.magnormSelector.removeEnabled = False
        self.magnormSelector.renameEnabled = False
        self.magnormSelector.showHidden = False
        self.magnormSelector.setMRMLScene(slicer.mrmlScene)
        assetLayout.addRow("MagNorm volume", self.magnormSelector)
        self.magnormSelector.currentNodeChanged.connect(lambda node: self._updateParameterNodeReference('magnormNodeID', node))

        self.magfieldSelector = slicer.qMRMLNodeComboBox(assetOverridesBox)
        self.magfieldSelector.nodeTypes = ["vtkMRMLTransformNode"]
        self.magfieldSelector.noneEnabled = True
        self.magfieldSelector.addEnabled = False
        self.magfieldSelector.removeEnabled = False
        self.magfieldSelector.renameEnabled = False
        self.magfieldSelector.showHidden = False
        self.magfieldSelector.setMRMLScene(slicer.mrmlScene)
        assetLayout.addRow("MagField transform", self.magfieldSelector)
        self.magfieldSelector.currentNodeChanged.connect(lambda node: self._updateParameterNodeReference('magfieldNodeID', node))

        self.conductivitySelector = slicer.qMRMLNodeComboBox(assetOverridesBox)
        self.conductivitySelector.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        self.conductivitySelector.noneEnabled = True
        self.conductivitySelector.addEnabled = False
        self.conductivitySelector.removeEnabled = False
        self.conductivitySelector.renameEnabled = False
        self.conductivitySelector.showHidden = False
        self.conductivitySelector.setMRMLScene(slicer.mrmlScene)
        assetLayout.addRow("Conductivity volume", self.conductivitySelector)
        self.conductivitySelector.currentNodeChanged.connect(lambda node: self._updateParameterNodeReference('conductivityNodeID', node))

        self.coilScaleSpinBox = qt.QDoubleSpinBox(assetOverridesBox)
        self.coilScaleSpinBox.setDecimals(2)
        self.coilScaleSpinBox.setMinimum(0.1)
        self.coilScaleSpinBox.setMaximum(100.0)
        self.coilScaleSpinBox.setValue(3.0)
        assetLayout.addRow("Coil scale", self.coilScaleSpinBox)
        self.coilScaleSpinBox.valueChanged.connect(self._onCoilScaleChanged)

        self.meshButton = qt.QCheckBox("Show Mesh", self.collapsibleButton)
        self.meshButton.checked = True
        self.formLayout.addRow(self.meshButton)
        self.meshButton.stateChanged.connect(L.Loader.showMesh)

        self.vouleRenderingButton = qt.QCheckBox("Show Volume Rendering", self.collapsibleButton)
        self.vouleRenderingButton.checked = False
        self.formLayout.addRow(self.vouleRenderingButton)
        self.vouleRenderingButton.stateChanged.connect(L.Loader.showVolumeRendering)

        self.layout.addStretch(1)

        # Current coil matrix display
        self.currentMatrixLabel = qt.QLabel("Current Matrix Position: ", self.collapsibleButton)
        self.layout.addWidget(self.currentMatrixLabel)
        self.matrixTextLabel = qt.QLabel("", self.collapsibleButton)
        self.layout.addWidget(self.matrixTextLabel)


        self.initialScalarArray = None
        self.layout.addStretch(1)
        self._restoreSelectionsFromParameterNode()

    def _setupTextConnector(self):
        # IGTL connections for sending dataset path to the server
        self.IGTLNode = slicer.vtkMRMLIGTLConnectorNode()
        slicer.mrmlScene.AddNode(self.IGTLNode)
        self.IGTLNode.SetName('TextConnector')
        self.IGTLNode.SetTypeClient('localhost', 18945)
        self.IGTLNode.Start()
        self.textNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLTextNode', 'DatasetPath')
        self.textNode.SetForceCreateStorageNode(True)
        self.IGTLNode.RegisterOutgoingMRMLNode(self.textNode)
        self.IGTLNode.PushOnConnect()

    def _defaultExamplePath(self):
        return os.path.abspath(os.path.join(os.path.dirname(slicer.modules.simulation.path), '../../data/Example1'))

    def _onBrowseDataDirectory(self):
        directory = qt.QFileDialog.getExistingDirectory(self.collapsibleButton, "Select data directory", self.examplePathEdit.text)
        if directory:
            self.examplePathEdit.text = directory

    def _resolveExamplePath(self, path_text):
        candidate = path_text.strip()
        if os.path.isdir(candidate):
            return os.path.abspath(candidate)
        alt_candidate = os.path.abspath(os.path.join(os.path.dirname(slicer.modules.simulation.path), '../', candidate))
        if os.path.isdir(alt_candidate):
            return alt_candidate
        raise FileNotFoundError(f"Could not find data directory: {candidate}")

    def sendExamplePathToServer(self, example_path):
        self.textNode.SetText(example_path)
        self.IGTLNode.PushNode(self.textNode)
        self.logMessage(f'Sent data directory to server: {example_path}')

    def onLoadExampleClicked(self):
        try:
            resolved_path = self._resolveExamplePath(self.examplePathEdit.text)
        except FileNotFoundError as exc:
            slicer.util.errorDisplay(str(exc))
            return

        self.example_path = resolved_path
        self.sendExamplePathToServer(resolved_path)
        overrides = self._collectOverrides()
        self.loader = L.Loader.loadExample(resolved_path, overrides)
        if self.loader:
            self.loader.setCoilMode(self._coilModeKey(self.coilModeCombo.currentText))

    def logMessage(self, *args):
        for arg in args:
            print(arg)

    def onCoilModeChanged(self, text):
        self.selectedCoilMode = text
        if self.loader:
            self.loader.setCoilMode(self._coilModeKey(text))

    @staticmethod
    def _coilModeKey(label):
        return "planned" if label == "Planned Pose" else "free"


    def _ensureParameterNode(self):
        try:
            self.parameterNode = slicer.util.getNode('SimulationParameters')
        except Exception:
            self.parameterNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLScriptedModuleNode', 'SimulationParameters')

    def _updateParameterNodeReference(self, key, node):
        if not self.parameterNode:
            return
        self.parameterNode.SetParameter(key, node.GetID() if node else '')

    def _onCoilScaleChanged(self, value):
        if not self.parameterNode:
            return
        self.parameterNode.SetParameter('coilScale', str(value))

    def _restoreSelectionsFromParameterNode(self):
        if not self.parameterNode:
            return
        self.coilSelector.setCurrentNodeID(self.parameterNode.GetParameter('coilModelNodeID') or None)
        self.skinSelector.setCurrentNodeID(self.parameterNode.GetParameter('skinModelNodeID') or None)
        self.magnormSelector.setCurrentNodeID(self.parameterNode.GetParameter('magnormNodeID') or None)
        self.magfieldSelector.setCurrentNodeID(self.parameterNode.GetParameter('magfieldNodeID') or None)
        self.conductivitySelector.setCurrentNodeID(self.parameterNode.GetParameter('conductivityNodeID') or None)
        coil_scale = self.parameterNode.GetParameter('coilScale')
        if coil_scale:
            try:
                self.coilScaleSpinBox.value = float(coil_scale)
            except ValueError:
                pass

    def _collectOverrides(self):
        def node_from_param(key):
            if not self.parameterNode:
                return None
            node_id = self.parameterNode.GetParameter(key)
            if not node_id:
                return None
            try:
                return slicer.mrmlScene.GetNodeByID(node_id)
            except Exception:
                return None

        overrides = {
            'coilModelNode': node_from_param('coilModelNodeID'),
            'skinModelNode': node_from_param('skinModelNodeID'),
            'magnormNode': node_from_param('magnormNodeID'),
            'magfieldTransform': node_from_param('magfieldNodeID'),
            'conductivityNode': node_from_param('conductivityNodeID'),
        }
        if self.parameterNode:
            coil_scale_val = self.parameterNode.GetParameter('coilScale')
            if coil_scale_val:
                try:
                    overrides['coilScale'] = float(coil_scale_val)
                except ValueError:
                    pass
        return overrides
