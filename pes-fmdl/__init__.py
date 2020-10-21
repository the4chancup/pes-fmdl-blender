bl_info = {
	"name": "PES FMDL format",
	"author": "foreground",
	"blender": (2, 79, 0),
	"category": "Import-Export",
	"version": (0, 5, 2),
}

from . import UI, Properties


def register():
	Properties.Properties.Register()
	UI.register()


def unregister():
	UI.unregister()
	Properties.Properties.Unregister()


if __name__ == "__main__":
	register()
