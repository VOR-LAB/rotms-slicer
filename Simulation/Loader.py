import os
import vtk, qt, ctk, slicer, sitkUtils
import SimpleITK as sitk
# from slicer.ScriptedLoadableModule import *
import numpy as np
import Rendering as ren
import Mapper as M


class Loader:

    def __init__(self, data_directory):
        self.data_directory = data_directory
        self._graymatter_file = 'gm'
        # the gray matter file can either be .stl or .vtk format:
        brainModelFile_stl = os.path.join(str(self.data_directory), self._graymatter_file + '.stl')
        brainModelFile_vtk = os.path.join(str(self.data_directory), self._graymatter_file + '.vtk')

        if os.path.isfile(brainModelFile_stl):
            brainModelFile = brainModelFile_stl
        elif os.path.isfile(brainModelFile_vtk):
            brainModelFile = brainModelFile_vtk
        else:
            return
        self._graymatter_file = os.path.basename(brainModelFile)

        self._coil_file = 'coil.stl'
        self._coil_scale = 3
        self._skin_file = 'skin.stl'
        self._magnorm_file = 'magnorm.nii.gz'
        self._magfield_file = 'magfield.nii.gz'
        self._conductivity_file = 'conductivity.nii.gz'

        self.modelNode = None
        self.coilNode = None
        self.skinNode = None
        self.markupsPlaneNode = None

        self.conductivityNode = None
        self.magfieldGTNode = None
        self.magfieldNode = None
        self.magnormNode = None
        self.efieldNode = None
        self.enormNode = None
        self.coilDefaultMatrix = vtk.vtkMatrix4x4()

        self.IGTLNode = None

        self.showMag = False #switch between magnetic and electric field for visualization
        self.coil_mode = 'free'
        self._planned_transform_observer = None
        self._updating_pose = False
        self.planned_transform_name = "Transform_9"

    def callMapper(self, param1=None, param2=None):
        if self._updating_pose:
            return
        M.Mapper.map(self, time=True)

    def showMesh(self):
        brainTransparentNode = slicer.util.getNode('brainTransparent')
        modelNode = slicer.util.getNode('gm')
        if self == 2:
            print("Show Brain Surface")
            modelNode.SetDisplayVisibility(1)
            brainTransparentNode.SetDisplayVisibility(0)
        elif self == 0:
            print("Hide Brain Surface")
            modelNode.SetDisplayVisibility(0)


    def showVolumeRendering(self):
        modelNode = slicer.util.getNode('gm')
        brainTransparentNode = slicer.util.getNode('brainTransparent')
        pyigtlNode = slicer.util.getNode('pyigtl_data')

        if self == 2:
            print("Show volume Rendering")
            modelNode.SetDisplayVisibility(0)
            brainTransparentNode.SetDisplayVisibility(1)
            pyigtlNode.SetDisplayVisibility(1)
            ren.Rendering.showVolumeRendering(pyigtlNode)

        elif self == 0:
            print("Hide Volume")
            brainTransparentNode.SetDisplayVisibility(0)
            pyigtlNode.SetDisplayVisibility(0)


    def newImage(self, caller, event):
        print('New CNN Image received via PyIgtl')
        M.Mapper.modifyIncomingImage(self)

#  this was @staticmethod before?
    @classmethod
    def loadExample(self, example_path, overrides=None):

        data_directory = Loader._resolve_data_directory(example_path)

        print('Your selected Example: ' + data_directory)

        loader = Loader(data_directory)
        overrides = overrides or {}
        if overrides.get('coilScale') is not None:
            loader._coil_scale = overrides['coilScale']

        # slicer.mrmlScene.Clear()

        #
        # 1. Brain:
        #
        brainModelFile = os.path.join( loader.data_directory, loader._graymatter_file )
        loader.modelNode = slicer.modules.models.logic().AddModel(brainModelFile,
                                                                slicer.vtkMRMLStorageNode.CoordinateSystemRAS)


        loader.brainTransparentNode = slicer.modules.models.logic().AddModel(brainModelFile,
                                                                slicer.vtkMRMLStorageNode.CoordinateSystemRAS)
        loader.brainTransparentNode.SetName('brainTransparent')
        brainTransparentDisplayNode = loader.brainTransparentNode.GetDisplayNode()
        brainTransparentDisplayNode.SetOpacity(0.3)
        brainTransparentDisplayNode.SetColor(0.7, 0.7, 0.7)
        loader.brainTransparentNode.SetDisplayVisibility(False)
        #
        # 2. Skin model:
        #
        skin = os.path.join( loader.data_directory, loader._skin_file )
        skin_override = overrides.get('skinModelNode')
        loader.skinNode = skin_override or slicer.modules.models.logic().AddModel(skin, slicer.vtkMRMLStorageNode.CoordinateSystemRAS)
        if not skin_override:
            skinDisplayNode = loader.skinNode.GetDisplayNode()
            skinDisplayNode.SetColor(0.8, 0.8, 0.8)
            skinDisplayNode.SetOpacity(0.35)


        #
        # 3. TMS coil:
        #
        coil = os.path.join( loader.data_directory, loader._coil_file )
        loader.coilNode = overrides.get('coilModelNode') or slicer.modules.models.logic().AddModel(coil, slicer.vtkMRMLStorageNode.CoordinateSystemRAS)
        
        # Set transform on the coil and resize it:
        parentTransform = vtk.vtkTransform()
        parentTransform.Scale(loader._coil_scale, loader._coil_scale, loader._coil_scale)
        
        loader.coilNode.ApplyTransformMatrix(parentTransform.GetMatrix())

        # Add a plane to the scene
        markupsPlaneNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLMarkupsPlaneNode', 'Coil')
        # markupsPlaneNode.SetOrigin([0, 0, 110])
        # markupsPlaneNode.SetOrigin([0, 0, 0])
        # markupsPlaneNode.SetNormalWorld([0, 0, -10])
        markupsPlaneNode.SetNormalWorld([0, 0, -1])
        markupsPlaneNode.SetAxes([.5, 0, 0], [0, .5, 0], [0, 0, .5])
        markupsPlaneNode.SetSize(10,10) # or SetPlaneBounds()
        markupsPlaneNode.GetMarkupsDisplayNode().SetHandlesInteractive(True)
        markupsPlaneNode.GetMarkupsDisplayNode().SetRotationHandleVisibility(1)
        markupsPlaneNode.GetMarkupsDisplayNode().SetTranslationHandleVisibility(1)
        markupsPlaneNode.GetMarkupsDisplayNode().SetOpacity(0.6)
        markupsPlaneNode.GetMarkupsDisplayNode().SetInteractionHandleScale(1.5)
        markupsPlaneNode.GetDisplayNode().SetSnapMode(slicer.vtkMRMLMarkupsDisplayNode.SnapModeToVisibleSurface)
        markupsPlaneNode.SetDisplayVisibility(1)

        loader.markupsPlaneNode = markupsPlaneNode

        loader.transformNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLinearTransformNode", "HandleTransform")

        # loader.transformNode = slicer.mrmlScene.AddNode(slicer.vtkMRMLLinearTransformNode())
        loader.coilNode.SetAndObserveTransformNodeID(loader.transformNode.GetID())
        # Keep plane independent; we use its world matrix to drive the coil transform
        loader.markupsPlaneNode.SetAndObserveTransformNodeID(None)

        # Align plane origin to coil center to avoid offsets
        if loader.coilNode.GetPolyData():
            cx, cy, cz = loader.coilNode.GetPolyData().GetCenter()
            loader.markupsPlaneNode.SetOrigin([cx, cy, cz])
        else:
            loader.markupsPlaneNode.SetOrigin([0, 0, 0])

        # Coil placement mode defaults to free; handles are on by default
        loader._setHandleVisibility(True)

        #
        # 4. Other stuff
        #

        # load magnorm (used for tesing and visualization, not useful for predicting E-field)
        magnorm_override = overrides.get('magnormNode')
        loader.magnormNode = magnorm_override or slicer.util.loadVolume( os.path.join( loader.data_directory, loader._magnorm_file ) )
        if not magnorm_override:
            loader.magnormNode.SetName('MagNorm')
        loader.magnormNode.GetIJKToRASMatrix(loader.coilDefaultMatrix)


        # load magvector as a GridTransformNode 
        # the grid transform node (GTNode) only provides the 4D vtkImageData in the original space
        loader.magfieldGTNode  = overrides.get('magfieldTransform') or slicer.util.loadTransform(os.path.join( loader.data_directory, loader._magfield_file ))

        # load conductivity
        conductivity_override = overrides.get('conductivityNode')
        loader.conductivityNode = conductivity_override or slicer.util.loadVolume( os.path.join( loader.data_directory, loader._conductivity_file ) )

        # creat magfield vector volumeNode for visualizing rotated RBG-coded magnetic vector field
        loader.magfieldNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLScalarVolumeNode')
        loader.magfieldNode.SetSpacing(loader.conductivityNode.GetSpacing())
        loader.magfieldNode.SetOrigin(loader.conductivityNode.GetOrigin())
        loader.magfieldNode.SetName('MagVec')

        # create nodes for received E-field data from pyigtl 
        loader.efieldNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLVectorVolumeNode')
        loader.efieldNode.Copy(loader.magfieldNode)
        loader.efieldNode.SetName('EVec')

        loader.enormNode = slicer.mrmlScene.AddNewNodeByClass('vtkMRMLScalarVolumeNode')
        loader.enormNode.Copy(loader.conductivityNode)
        loader.enormNode.SetName('ENorm')


        # IGTL connections
        loader.IGTLNode = slicer.vtkMRMLIGTLConnectorNode()
        slicer.mrmlScene.AddNode(loader.IGTLNode)
        # node should be visible in OpenIGTLinkIF module under connectors
        loader.IGTLNode.SetName('Connector1')
        # add command line stuff here
        loader.IGTLNode.SetTypeClient('localhost', 18944)
        # this will activate the the status of the connection:
        loader.IGTLNode.Start()
        loader.IGTLNode.RegisterIncomingMRMLNode(loader.efieldNode)
        loader.IGTLNode.RegisterOutgoingMRMLNode(loader.magfieldNode)
        loader.IGTLNode.PushOnConnect()
        print('OpenIGTLink Connector created! \n Check IGT > OpenIGTLinkIF and start external pyigtl server.')

        # observer for the icoming IGTL image data
        loader.pyigtlNode = slicer.util.loadVolume( os.path.join( loader.data_directory, loader._conductivity_file ) )
        # loader.pyigtlNode.Copy(loader.enormNode)
        loader.pyigtlNode.SetName('pyigtl_data')

        # Display setting
        # conductivityDisplayNode = loader.conductivityNode.GetDisplayNode()
        # conductivityDisplayNode.SetAndObserveColorNodeID('vtkMRMLColorTableNodeGrey')
        # conductivityDisplayNode.SetVisibility2D(True)

        pyigtlDisplayNode = loader.pyigtlNode.GetDisplayNode()
        pyigtlDisplayNode.AutoWindowLevelOff()
        pyigtlDisplayNode.SetWindowLevelMinMax(0.0, 1.0)
        pyigtlDisplayNode.SetLowerThreshold(0)
        pyigtlDisplayNode.SetUpperThreshold(1)
        pyigtlDisplayNode.SetAndObserveColorNodeID('vtkMRMLColorTableNodeFileColdToHotRainbow.txt')

        slicer.util.setSliceViewerLayers(background=loader.conductivityNode)
        slicer.util.setSliceViewerLayers(foreground=loader.pyigtlNode)
        slicer.util.setSliceViewerLayers(foregroundOpacity=0.6)
        slicer.app.processEvents()  # Dynamic updating scene

        observationTag = loader.pyigtlNode.AddObserver(slicer.vtkMRMLScalarVolumeNode.ImageDataModifiedEvent, loader.newImage)


        # # call one time
        loader.callMapper()

        # # interaction hookup
        loader.markupsPlaneNode.AddObserver(slicer.vtkMRMLMarkupsNode.PointModifiedEvent, loader.callMapper)
        #slicer.mrmlScene.AddObserver(slicer.vtkMRMLScene.NodeAddedEvent, loader.onNodeRcvd)

        return loader

    @staticmethod
    def _resolve_data_directory(example_path):
        if not example_path:
            raise FileNotFoundError("No data directory provided.")
        if os.path.isabs(example_path):
            candidate = example_path
        else:
            candidate = os.path.join(os.path.dirname(slicer.modules.slicertms.path), '../', example_path)
        candidate = os.path.abspath(candidate)
        if not os.path.isdir(candidate):
            raise FileNotFoundError(f"Data directory does not exist: {candidate}")
        return candidate

    #
    # Coil placement helpers
    #
    def _setHandleVisibility(self, visible: bool):
        if not self.markupsPlaneNode:
            return
        display_node = self.markupsPlaneNode.GetMarkupsDisplayNode()
        display_node.SetHandlesInteractive(1 if visible else 0)
        display_node.SetRotationHandleVisibility(1 if visible else 0)
        display_node.SetTranslationHandleVisibility(1 if visible else 0)

    def setCoilMode(self, mode: str):
        """mode: 'free' or 'planned'"""
        self.coil_mode = mode
        if mode == 'planned':
            self._setHandleVisibility(False)
            self._observePlannedTransform()
            self.callMapper()
        else:
            self._setHandleVisibility(True)
            self._removePlannedTransformObserver()

    def _observePlannedTransform(self):
        self._removePlannedTransformObserver()
        try:
            node = slicer.util.getNode(self.planned_transform_name)
        except Exception:
            slicer.util.errorDisplay(f"Planned transform '{self.planned_transform_name}' not found. Reverting to free mode.")
            self.coil_mode = 'free'
            self._setHandleVisibility(True)
            return
        self._planned_transform_observer = node.AddObserver(
            slicer.vtkMRMLTransformableNode.TransformModifiedEvent, self.callMapper)

    def _removePlannedTransformObserver(self):
        if not self._planned_transform_observer:
            return
        try:
            node = slicer.util.getNode(self.planned_transform_name)
            node.RemoveObserver(self._planned_transform_observer)
        except Exception:
            pass
        self._planned_transform_observer = None

    def applyCoilMatrix(self, matrix: vtk.vtkMatrix4x4):
        """Apply matrix to coil transform (plane stays independent)."""
        if self._updating_pose:
            return
        self._updating_pose = True
        try:
            self.transformNode.SetMatrixTransformToParent(matrix)
            if self.markupsPlaneNode:
                self.markupsPlaneNode.UpdateScene(slicer.mrmlScene)
            self.transformNode.UpdateScene(slicer.mrmlScene)
        finally:
            self._updating_pose = False

    def getPlannedMatrix(self):
        node = slicer.util.getNode(self.planned_transform_name)
        base_matrix = vtk.vtkMatrix4x4()
        node.GetMatrixTransformToParent(base_matrix)

        # Account for coil body frame: rotate 180 degrees about X after the planned transform
        rx180 = vtk.vtkMatrix4x4()
        rx180.DeepCopy((
            1, 0,  0, 0,
            0, -1, 0, 0,
            0, 0, -1, 0,
            0, 0,  0, 1
        ))

        dz = vtk.vtkMatrix4x4()
        dz.DeepCopy((
            1, 0, 0, 0,
            0, 1, 0, 0,
            0, 0, 1, -9.0,
            0, 0, 0, 1
        ))

        adjusted_matrix = vtk.vtkMatrix4x4()
        vtk.vtkMatrix4x4.Multiply4x4(base_matrix, rx180, adjusted_matrix)

        vtk.vtkMatrix4x4.Multiply4x4(adjusted_matrix, dz, adjusted_matrix)
        return adjusted_matrix
