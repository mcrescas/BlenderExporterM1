# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# System libs
import os, time, threading, sys, copy, subprocess

# Blender libs
import bpy, bl_ui, time

# Framework libs
from extensions_framework import util as efutil

from .. import MitsubaAddon, plugin_path

from ..outputs import MtsLog, MtsFilmDisplay
from ..export import (get_instance_materials, 
		resolution, MtsLaunch)
from ..export.scene import SceneExporter

from ..properties import (
	engine, sampler, integrator, lamp, texture,
	material, mesh, camera, world
);

from ..ui import (
	render, render_layer, lamps, materials, mesh, 
	camera, world
)

from ..ui.textures import (
	main, bitmap, checkerboard, gridtexture, mapping, scale, wireframe
)

from ..ui.materials import (
	main, subsurface, medium, emitter
)

from .. import operators

def _register_elm(elm, required=False):
	try:
		elm.COMPAT_ENGINES.add('MITSUBA_RENDER')
	except:
		pass

def compatible(mod):
	mod = getattr(bl_ui, mod)
	for subclass in mod.__dict__.values():
		try:
			subclass.COMPAT_ENGINES.add('MITSUBA_RENDER')
		except:
			pass
	del mod

_register_elm(bl_ui.properties_data_lamp.DATA_PT_context_lamp)
_register_elm(bl_ui.properties_render.RENDER_PT_render)
_register_elm(bl_ui.properties_render.RENDER_PT_dimensions)

# Add Mitsuba dof elements to blender dof panel
def mits_use_dof(self, context):
	
	if context.scene.render.engine == 'MITSUBA_RENDER':
		row = self.layout.row()
		
		row.prop(context.camera.mitsuba_camera, "useDOF", text="Use Depth of Field")
		if context.camera.mitsuba_camera.useDOF == True:
			row = self.layout.row()
			row.prop(context.camera.mitsuba_camera, "apertureRadius", text="DOF Aperture Radius")

_register_elm(bl_ui.properties_data_camera.DATA_PT_camera_dof.append(mits_use_dof))

compatible("properties_data_mesh")
compatible("properties_data_camera") #for displaying default panel in camera
compatible("properties_particle")

@MitsubaAddon.addon_register_class
class RENDERENGINE_mitsuba(bpy.types.RenderEngine):
	bl_idname			= 'MITSUBA_RENDER'
	bl_label			= 'Mitsuba'
	bl_use_preview		= True
	
	render_lock = threading.Lock()
	
	def render(self, scene):
		if self is None or scene is None:
			MtsLog('ERROR: Scene is missing!')
			return
		if scene.mitsuba_engine.binary_path == '':
			MtsLog('ERROR: The binary path is unspecified!')
			return
		
		with self.render_lock:	# just render one thing at a time
			if scene.name == 'preview':
				self.render_preview(scene)
				return
			
			config_updates = {}
			binary_path = os.path.abspath(efutil.filesystem_path(scene.mitsuba_engine.binary_path))
			if os.path.isdir(binary_path) and os.path.exists(binary_path):
				config_updates['binary_path'] = binary_path
			
			try:
				for k, v in config_updates.items():
					efutil.write_config_value('mitsuba', 'defaults', k, v)
			except Exception as err:
				MtsLog('WARNING: Saving Mitsuba configuration failed, please set your user scripts dir: %s' % err)
			
			scene_path = efutil.filesystem_path(scene.render.filepath)
			if os.path.isdir(scene_path):
				output_dir = scene_path
			else:
				output_dir = os.path.dirname(scene_path)		
			
			MtsLog('MtsBlend: Current directory = "%s"' % output_dir)
			output_basename = efutil.scene_filename() + '.%s.%05i' % (scene.name, scene.frame_current)
			
			result = SceneExporter(
				directory = output_dir,
				filename = output_basename,
			).export(scene)
			
			if not result:
				MtsLog('Error while exporting -- check the console for details.')
				return
			
			if scene.mitsuba_engine.export_mode == 'render':
				
				MtsLog("MtsBlend: Launching renderer ..")
				if scene.mitsuba_engine.render_mode == 'gui':
					MtsLaunch(scene.mitsuba_engine.binary_path, output_dir,
						['mtsgui', efutil.export_path])
				elif scene.mitsuba_engine.render_mode == 'cli':
					output_file = efutil.export_path[:-4] + "." + scene.camera.data.mitsuba_film.fileExtension
					mitsuba_process = MtsLaunch(scene.mitsuba_engine.binary_path, output_dir,
						['mitsuba', '-r', str(scene.mitsuba_engine.refresh_interval),
							'-o', output_file, efutil.export_path]
					)
					framebuffer_thread = MtsFilmDisplay()
					framebuffer_thread.set_kick_period(scene.mitsuba_engine.refresh_interval) 
					framebuffer_thread.begin(self, output_file, resolution(scene))
					render_update_timer = None
					while mitsuba_process.poll() == None and not self.test_break():
						render_update_timer = threading.Timer(1, self.process_wait_timer)
						render_update_timer.start()
						if render_update_timer.isAlive(): render_update_timer.join()
					
					# If we exit the wait loop (user cancelled) and mitsuba is still running, then send SIGINT
					if mitsuba_process.poll() == None:
						# Use SIGTERM because that's the only one supported on Windows
						mitsuba_process.send_signal(subprocess.signal.SIGTERM)
					
					# Stop updating the render result and load the final image
					framebuffer_thread.stop()
					framebuffer_thread.join()
					
					if mitsuba_process.poll() != None and mitsuba_process.returncode != 0:
						MtsLog("MtsBlend: Rendering failed -- check the console")
					else:
						framebuffer_thread.kick(render_end=True)
					framebuffer_thread.shutdown()
	
	def process_wait_timer(self):
		# Nothing to do here
		pass
	
	def render_preview(self, scene):
		# Iterate through the preview scene, finding objects with materials attached
		objects_materials = {}
		(width, height) = resolution(scene)
		
		if (width, height) == (96, 96):
			return
		MtsLog('Preview Render Res: {0}'.format(width, height))
		for object in [ob for ob in scene.objects if ob.is_visible(scene) and not ob.hide_render]:
			for mat in get_instance_materials(object):
				if mat is not None:
					if not object.name in objects_materials.keys(): objects_materials[object] = []
					objects_materials[object].append(mat)
		
		# find objects that are likely to be the preview objects
		preview_objects = [o for o in objects_materials.keys() if o.name.startswith('preview')]
		if len(preview_objects) < 1:
			return
		
		# find the materials attached to the likely preview object
		likely_materials = objects_materials[preview_objects[0]]
		if len(likely_materials) < 1:
			return
		
		tempdir = efutil.temp_directory()
		matfile = "matpreview_materials.xml"
		output_file = os.path.join(tempdir, "matpreview.png")
		scene_file = os.path.join(os.path.join(plugin_path(),
			"matpreview"), "matpreview.xml")
		MtsLog('Scene path: %s'%scene_file)
		pm = likely_materials[0]
		exporter = SceneExporter(tempdir, matfile,
			bpy.data.materials, bpy.data.textures)
		exporter.adj_filename = os.path.join(tempdir, matfile)
		if not exporter.writeHeader():
			MtsLog('Error while exporting -- check the console for details.')
			return;
		exporter.exportMaterial(pm)
		exporter.exportPreviewMesh(scene, pm)
		exporter.writeFooter()
		refresh_interval = 2
		preview_spp = int(efutil.find_config_value('mitsuba', 'defaults', 'preview_spp', '16'))
		preview_depth = int(efutil.find_config_value('mitsuba', 'defaults', 'preview_depth', '2'))
		
		mitsuba_process = MtsLaunch(scene.mitsuba_engine.binary_path, tempdir,
			['mitsuba', '-q', 
				'-r%i' % refresh_interval,
				'-b16',
				'-Dmatfile=%s' % os.path.join(tempdir, matfile),
				'-Dwidth=%i' % width, 
				'-Dheight=%i' % height, 
				'-Dspp=%i' % preview_spp,
				'-Ddepth=%i' % preview_depth,
				'-o', output_file, scene_file], )
		
		framebuffer_thread = MtsFilmDisplay()
		framebuffer_thread.set_kick_period(refresh_interval)
		framebuffer_thread.begin(self, output_file, resolution(scene), preview=True)
		render_update_timer = None
		while mitsuba_process.poll() == None and not self.test_break():
			render_update_timer = threading.Timer(1, self.process_wait_timer)
			render_update_timer.start()
			if render_update_timer.isAlive(): render_update_timer.join()
		
		cancelled = False
		# If we exit the wait loop (user cancelled) and mitsuba is still running, then send SIGINT
		if mitsuba_process.poll() == None:
			MtsLog("MtsBlend: Terminating process..")
			# Use SIGTERM because that's the only one supported on Windows
			mitsuba_process.send_signal(subprocess.signal.SIGTERM)
			cancelled = True
		
		# Stop updating the render result and load the final image
		framebuffer_thread.stop()
		framebuffer_thread.join()
		
		if not cancelled:
			if mitsuba_process.poll() != None and mitsuba_process.returncode != 0:
				MtsLog("MtsBlend: Rendering failed -- check the console"); mitsuba_process.send_signal(subprocess.signal.SIGTERM) #fixes mitsuba preview not refresing after bad eg. reference
			else:
				framebuffer_thread.kick(render_end=True)
		framebuffer_thread.shutdown()
