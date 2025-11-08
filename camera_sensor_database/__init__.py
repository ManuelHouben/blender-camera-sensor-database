import bpy
import urllib.request
import os
import json
from bpy.props import StringProperty, BoolProperty, EnumProperty, PointerProperty
from datetime import datetime

# --- Constants ---
SENSORS_URL = "https://raw.githubusercontent.com/EmberLightVFX/Camera-Sensor-Database/refs/heads/main/data/sensors.json"
API_URL = "https://api.github.com/repos/EmberLightVFX/Camera-Sensor-Database/contents/data/sensors.json"

# --- Global Data ---
SENSOR_DATA = {}

# --- Helper Functions ---
def get_sensors_file_path():
    """Get the path to the sensors.json file in the user's extension directory."""
    user_path = bpy.utils.extension_path_user(__package__, create=True)
    return os.path.join(user_path, 'sensors.json')

def load_sensor_data():
    """Load the sensor data from the JSON file into the global SENSOR_DATA dict."""
    global SENSOR_DATA
    file_path = get_sensors_file_path()
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                SENSOR_DATA = json.load(f)
            print("Camera Sensor Database: Loaded sensor data.")
        except json.JSONDecodeError:
            SENSOR_DATA = {}
            print("Camera Sensor Database: Error reading sensors.json file.")
    else:
        SENSOR_DATA = {}
        print("Camera Sensor Database: sensors.json not found.")

# --- Dynamic Enum Callbacks ---
def get_manufacturers(self, context):
    items = [(m, m, "") for m in SENSOR_DATA.keys()]
    return sorted(items) if items else [("NONE", "No Data Found", "Please download the database in Add-on Preferences.")]

def get_models(self, context):
    props = context.scene.csd_sensor_properties
    if not props.manufacturers or props.manufacturers == "NONE":
        return [("NONE", "N/A", "")]
    
    models = SENSOR_DATA.get(props.manufacturers, {}).keys()
    items = [(m, m, "") for m in models]
    return sorted(items) if items else [("NONE", "N/A", "")]
    
def get_formats(self, context):
    props = context.scene.csd_sensor_properties
    if not props.manufacturers or not props.models or props.manufacturers == "NONE" or props.models == "NONE":
        return [("NONE", "N/A", "")]
        
    formats = SENSOR_DATA.get(props.manufacturers, {}).get(props.models, {}).get("sensor dimensions", {}).keys()
    items = [(f, f, "") for f in formats]
    return sorted(items) if items else [("NONE", "N/A", "")]

# --- Property Group ---
class CSD_SensorProperties(bpy.types.PropertyGroup):
    
    manufacturers: EnumProperty(items=get_manufacturers, name="Manufacturer")
    models: EnumProperty(items=get_models, name="Model")
    formats: EnumProperty(items=get_formats, name="Format")

# --- Operators ---
class CSD_OT_ApplySensor(bpy.types.Operator):
    """Applies the selected sensor dimensions to the active camera."""
    bl_idname = "csd.apply_sensor"
    bl_label = "Apply Sensor"

    @classmethod
    def poll(cls, context):
        props = context.scene.csd_sensor_properties
        return context.camera is not None and props.formats and props.formats != "NONE"

    def execute(self, context):
        props = context.scene.csd_sensor_properties
        try:
            format_data = SENSOR_DATA[props.manufacturers][props.models]["sensor dimensions"][props.formats]["mm"]
            width = format_data.get("width")
            height = format_data.get("height")
            
            if width and height:
                cam_data = context.camera
                cam_data.sensor_fit = 'HORIZONTAL'
                cam_data.sensor_width = width
                cam_data.sensor_height = height
                self.report({'INFO'}, f"Sensor set to: {width}mm x {height}mm")
            else:
                self.report({'WARNING'}, "Selected format has no sensor data.")
                return {'CANCELLED'}

        except KeyError:
            self.report({'ERROR'}, "Could not apply sensor settings. Data not found.")
            return {'CANCELLED'}

        return {'FINISHED'}

class CSD_OT_ApplyResolution(bpy.types.Operator):
    """Applies the selected resolution to the scene's render settings."""
    bl_idname = "csd.apply_resolution"
    bl_label = "Apply Resolution"

    @classmethod
    def poll(cls, context):
        props = context.scene.csd_sensor_properties
        if not props.formats or props.formats == "NONE":
            return False
        
        try:
            res_data = SENSOR_DATA[props.manufacturers][props.models]["sensor dimensions"][props.formats]["resolution"]
            width = res_data.get("width")
            height = res_data.get("height")
            return isinstance(width, int) and isinstance(height, int)
        except (KeyError, TypeError):
            return False

    def execute(self, context):
        props = context.scene.csd_sensor_properties
        try:
            res_data = SENSOR_DATA[props.manufacturers][props.models]["sensor dimensions"][props.formats]["resolution"]
            width = res_data.get("width")
            height = res_data.get("height")

            if isinstance(width, int) and isinstance(height, int):
                context.scene.render.resolution_x = width
                context.scene.render.resolution_y = height
                self.report({'INFO'}, f"Resolution set to: {width} x {height}")
            else:
                self.report({'WARNING'}, "Selected format has no resolution data.")
                return {'CANCELLED'}

        except KeyError:
            self.report({'ERROR'}, "Could not apply resolution settings. Data not found.")
            return {'CANCELLED'}

        return {'FINISHED'}

class CSD_OT_CheckForUpdate(bpy.types.Operator):
    """Checks if a new sensor database is available."""
    bl_idname = "csd.check_for_update"
    bl_label = "Check for Update"

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        
        try:
            if not bpy.app.online_access:
                self.report({'WARNING'}, "Internet access is disabled.")
                return {'CANCELLED'}

            with urllib.request.urlopen(API_URL) as response:
                if response.status != 200:
                    self.report({'ERROR'}, f"Failed to check for updates (HTTP {response.status})")
                    return {'CANCELLED'}
                
                data = json.loads(response.read())
                remote_sha = data.get('sha')
                
                if remote_sha and remote_sha != prefs.remote_sha:
                    prefs.update_available = True
                    self.report({'INFO'}, "An update for the sensor database is available.")
                else:
                    prefs.update_available = False
                    self.report({'INFO'}, "Sensor database is up to date.")
                
                prefs.last_checked = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        
        except Exception as e:
            self.report({'ERROR'}, f"Update check failed: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}


class CSD_OT_UpdateSensors(bpy.types.Operator):
    """Downloads the latest sensor database."""
    bl_idname = "csd.update_sensors"
    bl_label = "Download Update"

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        file_path = get_sensors_file_path()

        try:
            if not bpy.app.online_access:
                self.report({'WARNING'}, "Internet access is disabled in Blender preferences. Cannot update sensor database.")
                return {'CANCELLED'}

            self.report({'INFO'}, f"Downloading sensor database from {SENSORS_URL}...")
            
            req = urllib.request.Request(SENSORS_URL)
            with urllib.request.urlopen(req) as response, open(file_path, 'wb') as out_file:
                out_file.write(response.read())

            # After downloading, we need to get the new SHA
            with urllib.request.urlopen(API_URL) as api_response:
                data = json.loads(api_response.read())
                prefs.remote_sha = data.get('sha')

            prefs.update_available = False
            prefs.last_checked = datetime.now().strftime("%B %d, %Y at %I:%M %p")
            self.report({'INFO'}, f"Sensor database saved to {file_path}")
            
            # Reload data after downloading
            load_sensor_data()
            
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to download or save sensor database: {e}")
            return {'CANCELLED'}


# --- Add-on Preferences ---
class CSD_AddonPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    remote_sha: StringProperty(name="Remote SHA", default="")
    last_checked: StringProperty(name="Last Checked", default="Never")
    update_available: BoolProperty(name="Update Available", default=False)

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Sensor Database")
        
        row = box.row()
        row.label(text=f"Last Checked: {self.last_checked}")
        
        if self.update_available:
            row = box.row()
            row.label(text="An update is available.", icon='INFO')
            row = box.row()
            row.operator(CSD_OT_UpdateSensors.bl_idname, icon='IMPORT')
        else:
            row = box.row()
            row.label(text="Database is up to date.")

        row = box.row()
        row.operator(CSD_OT_CheckForUpdate.bl_idname, icon='FILE_REFRESH')


# --- Panel ---
class CSD_PT_MainPanel(bpy.types.Panel):
    """Creates a Panel in the Camera properties window"""
    bl_label = "Camera Sensor Database"
    bl_idname = "DATA_PT_csd_main_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        return context.camera is not None

    def draw(self, context):
        layout = self.layout
        props = context.scene.csd_sensor_properties
        
        if not SENSOR_DATA:
            layout.label(text="Sensor database not found or is empty.")
            layout.label(text="Please update in Add-on Preferences.")
            return

        col = layout.column(align=True)
        col.prop(props, "manufacturers")
        
        # Prevent drawing model/format if manufacturer isn't selected
        if props.manufacturers and props.manufacturers != "NONE":
            col.prop(props, "models")
        
        # Prevent drawing format if model isn't selected
        if props.models and props.models != "NONE":
            col.prop(props, "formats")
            
            row = layout.row(align=True)
            row.operator(CSD_OT_ApplySensor.bl_idname)
            row.operator(CSD_OT_ApplyResolution.bl_idname)


# --- Register & Unregister ---
classes = (
    CSD_OT_ApplySensor,
    CSD_OT_ApplyResolution,
    CSD_OT_CheckForUpdate,
    CSD_OT_UpdateSensors,
    CSD_AddonPreferences,
    CSD_SensorProperties,
    CSD_PT_MainPanel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
        
    bpy.types.Scene.csd_sensor_properties = PointerProperty(type=CSD_SensorProperties)
    
    load_sensor_data()

def unregister():
    del bpy.types.Scene.csd_sensor_properties
        
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
