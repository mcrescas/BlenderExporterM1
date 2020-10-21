Mitsuba Blender Addon
---------------------

Authors: Wenzel Jakob, Bartosz Styperek, Francesc Juhé

This directory contains the addon for Mitsuba Renderer <-> Blender
integration. It is based on the excellent LuxBlend 2.5 code from
Luxrender project.

Mitsuba Blender exporter tries to convert Blender all scene information
to Mitsuba Renderer format. Custom properties panels are added to
Blender UI to set Mitsuba Renderer options and custom attributes.



Installation
------------

Copy this folder to Blender addons folder and then enable Mitsuba
addon on 'Addons > Render' section of Blender 'User Preferences' panel.
After enabling the addon, configure the 'Executable Path' setting in
'Mitsuba Engine Settings' render panel by selecting the folder where
Mitsuba Renderer binary is installed. Blender might have to be restarted
after configuring 'Exectuable Path' for Material preview to work.



Features
--------

Supports all Mitsuba integrators:

    Ambient Occlusion
    Direct Illumination
    Path tracer
    Simple volumetric path tracer
    Extended volumetric path tracer
    Bidirectional path tracer
    Photon mapper
    Progressive photon mapper
    Stochastic progressive photon mapper
    Primary Sample Space MLT
    Path Space MLT
    Energy redistribution PT
    Adjoint Particle Tracer
    Virtual Point Light (Hardware)
    Adaptive meta-integrator
    Irradiance caching 


Supported samplers:

    Sobol QMC sampler
    Hammersley QMC sampler
    Halton QMC sampler
    Low discrepancy
    Stratified
    Independent 


Other features included:

    Direct output of Mitsuba format scene and serialized mesh file
    Binary PLY mesh files output
    Partial export of mesh objects, avoids exporting already exported meshes
    Support for dupli objects and dupli groups
    Support for particle objects and groups
    Preliminary support for Blender Hair
    Basic SSS shader support
    Environment maps (only one allowed per scene):
     - HDR environment maps - using hemi light
     - Sun & sky environment map - using sun light
    Multiple materials per object support
    Dielectric material - glass
    Conductor material - metal



