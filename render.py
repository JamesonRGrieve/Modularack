import cadquery as cq

from abstract_component import ExplodableObject
from front_module import FrontModule, HardDriveBay
from rack_unit import RackUnit
from rack_unit_exploded_view import RackUnitExplodedView
from wall_segment import WallSegment


def show_component(component, name_suffix=""):
    """
    Show a component or explodable object in the viewer

    Args:
        component: Component or ExplodableObject to show
        name_suffix: Suffix to add to the name for identification
    """
    if isinstance(component, RackUnit):
        # Special handling for RackUnit
        show_object(component.floor, name=f"floor_{name_suffix}")

        # Show all wall segments
        for wall_type, segments in component.wall_segments.items():
            for i, segment in enumerate(segments):
                show_component(segment, f"{name_suffix}_{i}")

        # Show front modules
        for i, module in enumerate(component.front_modules):
            show_component(module, f"{name_suffix}_mod{i}")

    elif hasattr(component, "components") and isinstance(component.components, dict):
        # It's an ExplodableObject, show each component
        for comp_name, comp_obj in component.components.items():
            show_object(comp_obj, name=f"{component.name}_{comp_name}_{name_suffix}")

    elif hasattr(component, "wall_obj"):
        # It's a WallSegment with wall_obj
        show_object(component.wall_obj, name=f"{component.name}_{name_suffix}")

    elif hasattr(component, "object"):
        # It's a FrontModule with object property
        show_object(component.object, name=f"{component.name}_{name_suffix}")

    elif hasattr(component, "rack_units"):
        # It's a RackUnitExplodedView
        for i, rack_unit in enumerate(component.rack_units):
            show_component(
                rack_unit, f"{name_suffix}_{rack_unit.depth}_{rack_unit.height_units}U"
            )

    else:
        # It's a simple object
        obj_name = component.name if hasattr(component, "name") else "object"
        show_object(component, name=f"{obj_name}_{name_suffix}")


class FrontModule:
    """A module that can be added to the front panel of a rack unit"""

    def __init__(self, width_segments, height_segments, depth=1.0, name="module"):
        """
        Create a front panel module

        Args:
            width_segments: Number of horizontal segments (1-12)
            height_segments: Number of vertical segments
            depth: Depth of the module in inches
            name: Name of the module
        """
        self.width_segments = width_segments
        self.height_segments = height_segments
        self.depth = depth
        self.name = name
        self.object = None
        self.position = (0, 0)  # (segment_x, segment_y)
        self.parent_rack = None

    def create(self, segment_width, segment_height):
        """
        Create the 3D object for this module

        Args:
            segment_width: Width of each segment in inches
            segment_height: Height of each segment in inches
        """
        width = self.width_segments * segment_width
        height = self.height_segments * segment_height

        self.object = (
            cq.Workplane("YZ").box(width, height, self.depth).translate((0, 0, 0))
        )  # Position at origin initially

        return self

    def translate(self, vector):
        """Translate the module by the given vector"""
        if self.object:
            self.object = self.object.translate(vector)
        return self

    def show(self, name_suffix=""):
        """Show the module in the viewer"""
        if self.object:
            show_object(self.object, name=f"{self.name}_{name_suffix}")


class HardDriveBay(FrontModule):
    """A 3.5" hard drive bay module (1 segment high, 3 segments wide)"""

    def __init__(self, name="hdd_bay"):
        super().__init__(width_segments=3, height_segments=1, depth=1.5, name=name)

    def create(self, segment_width, segment_height):
        """Override to create a more detailed hard drive bay"""
        width = self.width_segments * segment_width
        height = self.height_segments * segment_height

        # Create basic shape
        self.object = (
            cq.Workplane("YZ").box(width, height, self.depth).translate((0, 0, 0))
        )

        # Add handle cutout
        handle_width = width * 0.8
        handle_height = height * 0.6
        handle_depth = self.depth * 0.3

        self.object = (
            self.object.faces(">X")  # Select front face
            .workplane()
            .rect(handle_width, handle_height)
            .cutBlind(-handle_depth)
        )

        return self


class RackUnit(ExplodableObject):
    def __init__(
        self,
        depth,
        width,
        height_units=1,
        wall_thickness=0.25,
        floor_thickness=0.125,
        explode=False,
        explosion_distance=5,
    ):
        """
        Create a server rack unit with specified dimensions

        Args:
            depth: Depth of the rack unit
            width: Width of the rack unit
            height_units: Height of the rack unit in U units (1U = 1.75")
            wall_thickness: Thickness of the walls
            floor_thickness: Thickness of the floor
            explode: Whether to explode the object immediately
            explosion_distance: Distance to explode components
        """
        super().__init__(explode, explosion_distance)

        self.depth = depth
        self.width = width
        self.height_units = height_units
        self.height = height_units * 1.75  # Convert U units to inches
        self.wall_thickness = wall_thickness
        self.floor_thickness = floor_thickness

        self.inner_depth = self.depth - 2 * self.wall_thickness
        self.inner_width = self.width - 2 * self.wall_thickness

        # Front panel grid dimensions
        self.segments_width = 12
        self.segments_height = 2 * self.height_units  # 2 segments per U
        self.segment_width = self.width / self.segments_width
        self.segment_height = self.height / self.segments_height

        # Grid occupancy tracking
        self.grid_occupancy = [
            [False for _ in range(self.segments_width)]
            for _ in range(self.segments_height)
        ]

        # Components
        self.floor = None

        # Wall segments
        self.wall_segments = {"front": [], "back": [], "left": [], "right": []}

        # Front modules
        self.front_modules = []

        # Create the components
        self._create_components()

        # Explode if requested
        if explode:
            self.explode(explosion_distance)

    def _create_components(self):
        """Create the basic components (floor and walls)"""
        # Floor centered at origin initially
        self.floor = (
            cq.Workplane("XY")
            .box(self.depth, self.width, self.floor_thickness)
            .translate((self.depth / 2, 0, self.floor_thickness / 2))
        )

        # Add floor to components
        self.add_component("floor", self.floor)

        # Create wall segments based on height
        # For 1U, use a single 1U segment for each wall
        # For 2U, use a single 2U segment for each wall
        # For 3U, use one 2U + one 1U segment for each wall
        # For 4U, use two 2U segments for each wall

        segments_config = []
        if self.height_units == 1:
            segments_config = [1]
        elif self.height_units == 2:
            segments_config = [2]
        elif self.height_units == 3:
            segments_config = [2, 1]
        elif self.height_units == 4:
            segments_config = [2, 2]
        else:
            # For any other height, use 2U segments as much as possible, then add a 1U if needed
            segments_config = [2] * (self.height_units // 2)
            if self.height_units % 2 == 1:
                segments_config.append(1)

        # Create all wall segments
        for wall_type in ["front", "back", "left", "right"]:
            current_height = 0
            segments = []

            for i, seg_height in enumerate(segments_config):
                # Create the wall segment
                segment = WallSegment(
                    wall_type=wall_type,
                    width=self.width,
                    depth=self.depth,
                    height_units=seg_height,
                    thickness=self.wall_thickness,
                    name=f"{wall_type}_wall_{seg_height}U_{i}",
                    explode=False,
                    explosion_distance=self.explosion_distance,
                )

                # Store vertical position information for explosion
                segment.vertical_position = current_height
                segment.vertical_index = i
                segment.total_segments = len(segments_config)

                # Position the segment
                if wall_type == "front":
                    # Front wall at x=0
                    segment.translate(
                        (
                            self.wall_thickness / 2,
                            0,
                            current_height + segment.height / 2,
                        )
                    )
                elif wall_type == "back":
                    # Back wall at x=depth
                    segment.translate(
                        (
                            self.depth - self.wall_thickness / 2,
                            0,
                            current_height + segment.height / 2,
                        )
                    )
                elif wall_type == "left":
                    # Left wall along -y
                    segment.translate(
                        (
                            self.depth / 2,
                            -self.width / 2 + self.wall_thickness / 2,
                            current_height + segment.height / 2,
                        )
                    )
                elif wall_type == "right":
                    # Right wall along +y
                    segment.translate(
                        (
                            self.depth / 2,
                            self.width / 2 - self.wall_thickness / 2,
                            current_height + segment.height / 2,
                        )
                    )

                segments.append(segment)
                current_height += segment.height

                # Add to components dictionary with unique name
                self.add_component(f"{wall_type}_wall_{i}", segment.wall_obj)

            # Store segments
            self.wall_segments[wall_type] = segments

    def is_grid_position_available(
        self, segment_x, segment_y, width_segments, height_segments
    ):
        """
        Check if the specified grid position is available

        Args:
            segment_x: Starting X segment (0-11)
            segment_y: Starting Y segment (0 to segments_height-1)
            width_segments: Number of horizontal segments needed
            height_segments: Number of vertical segments needed

        Returns:
            True if position is available, False otherwise
        """
        # Check boundaries
        if (
            segment_x < 0
            or segment_x + width_segments > self.segments_width
            or segment_y < 0
            or segment_y + height_segments > self.segments_height
        ):
            return False

        # Check if any segment in the range is already occupied
        for y in range(segment_y, segment_y + height_segments):
            for x in range(segment_x, segment_x + width_segments):
                if self.grid_occupancy[y][x]:
                    return False

        return True

    def mark_grid_position(
        self, segment_x, segment_y, width_segments, height_segments, occupied=True
    ):
        """Mark grid positions as occupied or free"""
        for y in range(segment_y, segment_y + height_segments):
            for x in range(segment_x, segment_x + width_segments):
                self.grid_occupancy[y][x] = occupied

    def add_front_module(self, module, segment_x, segment_y):
        """
        Add a module to the front panel at the specified grid position

        Args:
            module: FrontModule instance
            segment_x: Starting X segment (0-11)
            segment_y: Starting Y segment (0 to segments_height-1)

        Returns:
            True if added successfully, False otherwise
        """
        # Check if position is available
        if not self.is_grid_position_available(
            segment_x, segment_y, module.width_segments, module.height_segments
        ):
            return False

        # Mark position as occupied
        self.mark_grid_position(
            segment_x, segment_y, module.width_segments, module.height_segments
        )

        # Create and position the module
        module.position = (segment_x, segment_y)
        module.parent_rack = self
        module.create(self.segment_width, self.segment_height)

        # Calculate the position in 3D space
        # Y position: shift from center by segment position
        pos_y = -self.width / 2 + self.segment_width * (
            segment_x + module.width_segments / 2
        )

        # Z position: position based on segment height from bottom
        pos_z = self.segment_height * (segment_y + module.height_segments / 2)

        # X position: at the front wall with slight offset
        pos_x = 0 + self.wall_thickness + 0.01

        # Position module
        module.translate((pos_x, pos_y, pos_z))

        # Add to modules list
        self.front_modules.append(module)

        return True

    def add_hard_drive_bays(self, fill_pattern="all"):
        """
        Add hard drive bays to the front panel

        Args:
            fill_pattern: "all" to fill all available space, or specific pattern
        """
        if fill_pattern == "all":
            # Fill with as many bays as possible (3 wide, 1 high)
            for y in range(0, self.segments_height):
                for x in range(0, self.segments_width, 3):
                    # Check if this position is available
                    if self.is_grid_position_available(x, y, 3, 1):
                        bay = HardDriveBay(name=f"hdd_bay_{x}_{y}")
                        self.add_front_module(bay, x, y)

    def explode(self, distance=None):
        """
        Explode the components outward by the specified distance

        Args:
            distance: Distance to explode components
        """
        if distance is None:
            distance = self.explosion_distance

        super().explode(distance)

        # Explode all wall segments
        for wall_type, segments in self.wall_segments.items():
            # Calculate vertical explosion distance
            vertical_explosion = distance * 0.75

            for i, segment in enumerate(segments):
                # Horizontal explosion (standard)
                segment.explode(distance)

                # Additional vertical explosion based on position
                if len(segments) > 1:
                    # For segments above the bottom, move them up
                    if i > 0:
                        vertical_shift = i * vertical_explosion
                        segment.translate((0, 0, vertical_shift))

                # Update component reference
                self.components[f"{wall_type}_wall_{i}"] = segment.wall_obj

        # Explode front modules forward (in negative X direction)
        # Position them in front of the exploded front wall
        for module in self.front_modules:
            module.translate((-distance * 1.5, 0, 0))

        return self

    def unexplode(self):
        """
        Restore components to their original positions
        """
        if not self.exploded:
            return self

        distance = self.explosion_distance
        vertical_explosion = distance * 0.75

        # Unexplode all wall segments
        for wall_type, segments in self.wall_segments.items():
            for i, segment in enumerate(segments):
                # First undo the vertical explosion for segments above the bottom
                if len(segments) > 1 and i > 0:
                    vertical_shift = i * vertical_explosion
                    segment.translate((0, 0, -vertical_shift))

                # Then standard unexplode
                segment.unexplode()

                # Update component reference
                self.components[f"{wall_type}_wall_{i}"] = segment.wall_obj

        # Move front modules back
        for module in self.front_modules:
            module.translate((distance * 1.5, 0, 0))

        super().unexplode()
        return self

    def translate(self, vector):
        """
        Translate all components by the specified vector

        Args:
            vector: (x, y, z) translation vector
        """
        # Translate floor
        self.floor = self.floor.translate(vector)
        self.components["floor"] = self.floor

        # Translate all wall segments
        for wall_type, segments in self.wall_segments.items():
            for i, segment in enumerate(segments):
                segment.translate(vector)
                # Update component reference
                self.components[f"{wall_type}_wall_{i}"] = segment.wall_obj

        # Translate front modules
        for module in self.front_modules:
            module.translate(vector)

        return self

    def get_practical_dimensions(self, explosion_distance=None):
        """
        Calculate practical dimensions including explosion distances

        Args:
            explosion_distance: Distance of explosion for calculating practical dimensions

        Returns:
            (practical_x, practical_y, practical_z) tuple
        """
        if explosion_distance is None:
            explosion_distance = self.explosion_distance

        # Add extra distance for front modules
        module_depth = (
            max([m.depth for m in self.front_modules]) if self.front_modules else 0
        )

        # If exploded, account for the explosion distance
        explosion_factor = 2 if self.exploded else 0

        practical_x = self.depth + explosion_factor * explosion_distance + module_depth
        practical_y = self.width + explosion_factor * explosion_distance
        practical_z = self.height

        return (practical_x, practical_y, practical_z)

    def show(self, name_suffix=""):
        """
        Show all components in the viewer

        Args:
            name_suffix: Suffix to add to component names for identification
        """
        show_object(self.floor, name=f"floor_{name_suffix}")

        # Show all wall segments
        for wall_type, segments in self.wall_segments.items():
            for i, segment in enumerate(segments):
                show_component(segment, f"{name_suffix}_{i}")

        # Show front modules
        for i, module in enumerate(self.front_modules):
            module.show(f"{name_suffix}_mod{i}")


class RackUnitExplodedView:
    def __init__(self, explosion_distance=5, gap_between_units=15):
        """
        Create an exploded view of multiple rack units

        Args:
            explosion_distance: Distance to explode components
            gap_between_units: Gap between rack units
        """
        self.explosion_distance = explosion_distance
        self.gap_between_units = gap_between_units
        self.rack_units = []

    def add_rack_unit(
        self,
        depth,
        width,
        height_units=1,
        wall_thickness=0.25,
        floor_thickness=0.125,
        modules_config=None,
        explode=False,
    ):
        """
        Add a rack unit to the view

        Args:
            depth: Depth of the rack unit
            width: Width of the rack unit
            height_units: Height of the rack unit in U units (1U = 1.75")
            wall_thickness: Thickness of the walls
            floor_thickness: Thickness of the floor
            modules_config: Configuration for front modules
            explode: Whether to create the unit in exploded state

        Returns:
            The created RackUnit object
        """
        rack_unit = RackUnit(
            depth,
            width,
            height_units,
            wall_thickness,
            floor_thickness,
            explode=explode,
            explosion_distance=self.explosion_distance,
        )

        # Add front modules based on configuration
        if modules_config == "hdd_bays" or modules_config == "full":
            # Fill all spaces with hard drive bays
            rack_unit.add_hard_drive_bays("all")

        self.rack_units.append(rack_unit)
        return rack_unit

    def arrange(self):
        """Arrange the rack units with front alignment and proper spacing"""
        # Explode all rack units that aren't already exploded
        for rack_unit in self.rack_units:
            if not rack_unit.exploded:
                rack_unit.explode(self.explosion_distance)

        # Calculate y positions
        y_positions = []
        current_y = 0

        for i, rack_unit in enumerate(self.rack_units):
            practical_dims = rack_unit.get_practical_dimensions(self.explosion_distance)

            if i == 0:
                # First unit centered at 0
                y_positions.append(0)
                current_y += practical_dims[1] / 2 + self.gap_between_units
            else:
                # Position based on previous unit's dimensions plus gap
                current_y += practical_dims[1] / 2
                y_positions.append(current_y)
                current_y += practical_dims[1] / 2 + self.gap_between_units

        # Position rack units
        for i, rack_unit in enumerate(self.rack_units):
            y_offset = y_positions[i]
            # No x offset needed - already front-aligned when created
            rack_unit.translate((0, y_offset, 0))

    def show(self):
        """Show all rack units"""
        for rack_unit in self.rack_units:
            rack_unit.show(name_suffix=f"{rack_unit.depth}_{rack_unit.height_units}U")


# Main code
if __name__ == "__main__" or True:  # True to ensure this runs in any environment
    # Rack dimensions
    rack_total_width = 19
    rack_chassis_width = 17.75
    rack_ear_width = rack_total_width - rack_chassis_width
    rack_unit_depths = [36, 42, 48, 50]

    # Create exploded view
    view = RackUnitExplodedView(explosion_distance=5, gap_between_units=15)

    # Add rack units with different heights but all with full drive bay populations
    # 1U
    view.add_rack_unit(
        rack_unit_depths[0], rack_chassis_width, 1, modules_config="full", explode=True
    )

    # 2U
    view.add_rack_unit(
        rack_unit_depths[1], rack_chassis_width, 2, modules_config="full", explode=True
    )

    # 3U (new)
    view.add_rack_unit(
        rack_unit_depths[2], rack_chassis_width, 3, modules_config="full", explode=True
    )

    # 4U
    view.add_rack_unit(
        rack_unit_depths[3], rack_chassis_width, 4, modules_config="full", explode=True
    )

    # Arrange and show
    view.arrange()
    show_component(view)
