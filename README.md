blender-mesh-connect
======================

Blender addon that introduces Connect and Deselect Boundary operations.

Deselect Boundary does the reverse of built-in Select Boundary Loop operator: given a selection of faces, it deselects its boundary loop.

Connect utilizes such selection mechanism to perform localized loop cuts. It operates on a selection of faces (can be disjoint), or edges (must be non-loop neighbors) and cuts through them, "connecting" them with edges.
The behavior differs slightly depending on whether you have face selection mode active, as the operator will follow the flow of faces.

After activating the addon, you'll find the operators in edit mode, menu Select -> Deselect Boundary and Edge -> Connect, Face -> Connect, or via the search menu.

Installation
============

Download zip, start Blender, go to User Preferences -> Addons, choose "Install From File" at the bottom and point it to downloaded archive. The addon will appear in the Mesh category.
