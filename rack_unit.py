import cadquery as cq

from abstract_component import AbstractComponent
from front_panel_3_5_inch import FrontPanel3_5Inch
from wall_segment import WallSegment


class RackChassis(AbstractComponent):
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
        self.name = f"rack_chassis_{height_units}U"

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

        # Create the components
        self._create_components()

        # Explode if requested
        if explode:
            self.explode(explosion_distance)

    def _create_components(self):
        """Create the basic components (floor and walls)"""
        # Floor centered at origin initially
        floor = (
            cq.Workplane("XY")
            .box(self.depth, self.width, self.floor_thickness)
            .translate((self.depth / 2, 0, self.floor_thickness / 2))
        )

        # Add floor to components - mark it as always visible
        self.add_component("floor", floor, always_visible=True)

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

                # Add as a child component with unique name
                # Note: We do not need to separately add the wall object to components
                # as add_child_component will already handle this
                self.add_child_component(f"{wall_type}_wall_{i}", segment)
                current_height += segment.height

    def get_main_object(self):
        """Return the floor as the main object"""
        return self.get_component("floor")

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
            module: AbstractFrontPanelComponent instance
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

        # Add as a child component
        self.add_child_component(f"front_module_{segment_x}_{segment_y}", module)

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
                        bay = FrontPanel3_5Inch(name=f"hdd_bay_{x}_{y}")
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

        # Additional vertical explosion for wall segments
        vertical_explosion = distance * 0.75

        # Get all wall segments
        for wall_type in ["front", "back", "left", "right"]:
            # Find all wall segments of this type
            segments = [
                comp
                for name, comp in self.child_components.items()
                if name.startswith(f"{wall_type}_wall_")
            ]

            # Sort segments by their vertical index if available
            segments.sort(key=lambda s: getattr(s, "vertical_index", 0))

            # Apply additional vertical spacing for segments above the bottom
            for i, segment in enumerate(segments):
                if i > 0:  # Skip the bottom segment
                    vertical_shift = i * vertical_explosion
                    segment.translate((0, 0, vertical_shift))

        return self

    def unexplode(self):
        """
        Restore components to their original positions
        """
        if not self.exploded:
            return self

        vertical_explosion = self.explosion_distance * 0.75

        # Undo additional vertical explosion for wall segments
        for wall_type in ["front", "back", "left", "right"]:
            # Find all wall segments of this type
            segments = [
                comp
                for name, comp in self.child_components.items()
                if name.startswith(f"{wall_type}_wall_")
            ]

            # Sort segments by their vertical index if available
            segments.sort(key=lambda s: getattr(s, "vertical_index", 0))

            # Undo additional vertical spacing for segments above the bottom
            for i, segment in enumerate(segments):
                if i > 0:  # Skip the bottom segment
                    vertical_shift = i * vertical_explosion
                    segment.translate((0, 0, -vertical_shift))

        super().unexplode()
        return self

    def translate(self, vector):
        """
        Translate all components by the specified vector

        Args:
            vector: (x, y, z) translation vector
        """
        # Translate floor
        floor = self.get_component("floor")
        if floor:
            floor = floor.translate(vector)
            self.add_component("floor", floor)

        # Child components are automatically translated by parent's translate
        super().translate(vector)

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
        front_modules = [
            comp
            for name, comp in self.child_components.items()
            if name.startswith("front_module_")
        ]
        module_depth = max([m.depth for m in front_modules]) if front_modules else 0

        # If exploded, account for the explosion distance
        explosion_factor = 2 if self.exploded else 0

        practical_x = self.depth + explosion_factor * explosion_distance + module_depth
        practical_y = self.width + explosion_factor * explosion_distance
        practical_z = self.height

        return (practical_x, practical_y, practical_z)
