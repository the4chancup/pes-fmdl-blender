import bpy
from bpy.types import Operator, AddonPreferences
from bpy.props import StringProperty


class PesFmdlPreferences(AddonPreferences):
	bl_idname = __package__
	
	texconv_path: StringProperty(
		name="Path to textconv.exe:",
		subtype='FILE_PATH',
	)
	
	def draw(self, context):
		self.layout.prop(self, "texconv_path")
