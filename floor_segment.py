import cadquery as cq

from abstract_component import AbstractComponent


class FloorSegment(AbstractComponent):
    """A segment of a rack unit floor that can accommodate different motherboard form factors"""

    FORM_FACTORS = ["mini-itx", "micro-atx", "atx", "e-atx"]

    # Conversion factor with high precision: 25.4 mm = 1 inch
    MM_TO_INCH = 1.0 / 25.4

    # Motherboard dimensions in mm (exact values)
    MINI_ITX_SIZE = (170.0, 170.0)  # Width, Depth in mm
    MICRO_ATX_SIZE = (244.0, 244.0)  # Width, Depth in mm
    ATX_SIZE = (305.0, 244.0)  # Width, Depth in mm
    E_ATX_SIZE = (305.0, 330.0)  # Width, Depth in mm

    # Standoff positions from the diagrams (in mm, relative to bottom-left corner)
    # Format: [(x1, y1), (x2, y2), ...]
    MINI_ITX_STANDOFFS = [
        (6.35, 6.35),  # Bottom-left
        (6.35, 170.0 - 6.35),  # Top-left
        (170.0 - 6.35, 6.35),  # Bottom-right
        (170.0 - 6.35, 170.0 - 6.35),  # Top-right
    ]

    MICRO_ATX_STANDOFFS = [
        (6.35, 6.35),  # Bottom-left
        (6.35, 244.0 - 6.35),  # Top-left
        (244.0 - 6.35, 6.35),  # Bottom-right
        (244.0 - 6.35, 244.0 - 6.35),  # Top-right
        # Additional standoffs unique to Micro-ATX
        (244.0 / 2, 6.35),  # Bottom-middle
        (244.0 / 2, 244.0 - 6.35),  # Top-middle
        (6.35, 244.0 / 2),  # Middle-left
        (244.0 - 6.35, 244.0 / 2),  # Middle-right
    ]

    # From the detailed diagram with precise measurements
    ATX_STANDOFFS = [
        # Standoffs from the diagram (in mm from bottom-left corner)
        (6.35, 6.35),  # Bottom-left
        (6.35, 154.94),  # Top-left
        (6.35 + 78.74, 6.35),  # Bottom-middle-left
        (6.35 + 45.72, 154.94),  # Top-middle-left
        (6.35 + 45.72 + 157.48, 6.35),  # Bottom-right
        (6.35 + 45.72 + 157.48, 154.94),  # Top-right
        (6.35 + 45.72 + 20.78 / 2, 154.94 + 72.39),  # Top extension
        (6.35 + 45.72 + 20.78 / 2 + 157.48, 154.94 + 72.39),  # Top-right extension
    ]

    E_ATX_STANDOFFS = [
        # Using ATX standoffs plus E-ATX extensions
        (6.35, 6.35),  # Bottom-left
        (6.35, 154.94),  # Top-left
        (6.35 + 78.74, 6.35),  # Bottom-middle-left
        (6.35 + 45.72, 154.94),  # Top-middle-left
        (6.35 + 45.72 + 157.48, 6.35),  # Bottom-right
        (6.35 + 45.72 + 157.48, 154.94),  # Top-right
        (6.35 + 45.72 + 20.78 / 2, 154.94 + 72.39),  # Top extension
        (6.35 + 45.72 + 20.78 / 2 + 157.48, 154.94 + 72.39),  # Top-right extension
        # E-ATX specific standoffs
        (6.35, 154.94 + 72.39 + 132.08 - 29.21),  # Far top-left
        (6.35 + 45.72 + 157.48, 154.94 + 72.39 + 132.08 - 29.21),  # Far top-right
    ]

    def __init__(
        self,
        form_factor,
        width,
        depth,
        thickness=0.125,
        name=None,
        position="center",
        explode=False,
        explosion_distance=5,
    ):
        """
        Create a floor segment for a specific motherboard form factor

        Args:
            form_factor: Motherboard form factor ("mini-itx", "micro-atx", "atx", "e-atx")
            width: Width of the floor segment
            depth: Depth of the floor segment
            thickness: Thickness of the floor segment
            name: Name of the segment
            position: Position of this segment ("center", "front", "back", "left", "right")
            explode: Whether to explode the object immediately
            explosion_distance: Distance to explode components
        """
        if form_factor not in self.FORM_FACTORS:
            raise ValueError(f"Form factor must be one of {self.FORM_FACTORS}")

        super().__init__(explode, explosion_distance)

        self.form_factor = form_factor
        self.width = width
        self.depth = depth
        self.thickness = thickness
        self.position = position
        self.name = name or f"floor_{form_factor}_{position}"

        # Calculated dimensions based on form factor
        self._calculate_dimensions()

        # Vertical positioning information (set by parent when added)
        self.vertical_position = 0
        self.vertical_index = 0
        self.total_segments = 1

        # Create the component
        self._create_components()

        # Explode if requested
        if explode:
            self.explode(explosion_distance)

    def _mm_to_inch(self, mm_value):
        """
        Convert millimeters to inches with high precision

        Args:
            mm_value: Value in millimeters

        Returns:
            Value in inches with high precision
        """
        return mm_value * self.MM_TO_INCH

    def _calculate_dimensions(self):
        """Calculate segment dimensions based on form factor"""
        # Convert motherboard dimensions from mm to inches with high precision
        mini_itx_width = self._mm_to_inch(self.MINI_ITX_SIZE[0])
        mini_itx_depth = self._mm_to_inch(self.MINI_ITX_SIZE[1])
        micro_atx_width = self._mm_to_inch(self.MICRO_ATX_SIZE[0])
        micro_atx_depth = self._mm_to_inch(self.MICRO_ATX_SIZE[1])
        atx_width = self._mm_to_inch(self.ATX_SIZE[0])
        atx_depth = self._mm_to_inch(self.ATX_SIZE[1])
        e_atx_width = self._mm_to_inch(self.E_ATX_SIZE[0])
        e_atx_depth = self._mm_to_inch(self.E_ATX_SIZE[1])

        # For simplicity, we'll create a single complete floor with required standoffs
        # rather than trying to subdivide it
        self.segment_width = self.width
        self.segment_depth = self.depth
        self.offset_x = 0
        self.offset_y = 0

        # Store the motherboard dimension information for standoff placement
        self.mini_itx_width_inch = mini_itx_width
        self.mini_itx_depth_inch = mini_itx_depth
        self.micro_atx_width_inch = micro_atx_width
        self.micro_atx_depth_inch = micro_atx_depth
        self.atx_width_inch = atx_width
        self.atx_depth_inch = atx_depth
        self.e_atx_width_inch = e_atx_width
        self.e_atx_depth_inch = e_atx_depth

    def _create_components(self):
        """Create the floor segment with appropriate standoff pattern"""
        # Skip if segment has no area
        if self.segment_width <= 0 or self.segment_depth <= 0:
            return self

        # Create basic floor plate
        floor_obj = (
            cq.Workplane("XY")
            .box(self.segment_depth, self.segment_width, self.thickness)
            .translate((self.depth / 2, 0, self.thickness / 2))
        )

        # Add standoff holes based on form factor
        if self.form_factor == "mini-itx":
            floor_obj = self._add_mini_itx_standoffs(floor_obj)
        elif self.form_factor == "micro-atx":
            floor_obj = self._add_mini_itx_standoffs(floor_obj)
            floor_obj = self._add_micro_atx_standoffs(floor_obj)
        elif self.form_factor == "atx":
            floor_obj = self._add_mini_itx_standoffs(floor_obj)
            floor_obj = self._add_micro_atx_standoffs(floor_obj)
            floor_obj = self._add_atx_standoffs(floor_obj)
        elif self.form_factor == "e-atx":
            floor_obj = self._add_mini_itx_standoffs(floor_obj)
            floor_obj = self._add_micro_atx_standoffs(floor_obj)
            floor_obj = self._add_atx_standoffs(floor_obj)
            floor_obj = self._add_e_atx_standoffs(floor_obj)

        # Add to components dictionary
        self.add_component("floor", floor_obj)

        return self

    def _add_mini_itx_standoffs(self, floor_obj):
        """Add Mini-ITX standoff pattern to the floor object"""
        # The standoff positions in mm from bottom-left, converted to inches with high precision
        standoff_positions_inch = [
            (self._mm_to_inch(x), self._mm_to_inch(y))
            for x, y in self.MINI_ITX_STANDOFFS
        ]

        # Calculate center position in the overall chassis
        chassis_center_x = self.depth / 2
        chassis_center_y = 0  # Y is centered at 0

        # Calculate mini-ITX board bottom-left corner position
        board_bl_x = chassis_center_x - self.mini_itx_depth_inch / 2
        board_bl_y = chassis_center_y - self.mini_itx_width_inch / 2

        # Add standoffs
        for pos in standoff_positions_inch:
            # Convert from board coordinates to chassis coordinates
            x = (
                board_bl_x + pos[1]
            )  # Note: x in CadQuery = depth in our coordinate system
            y = (
                board_bl_y + pos[0]
            )  # Note: y in CadQuery = width in our coordinate system
            floor_obj = self._add_standoff(floor_obj, x, y)

        return floor_obj

    def _add_micro_atx_standoffs(self, floor_obj):
        """Add Micro-ATX standoff pattern to the floor object"""
        # The standoff positions in mm from bottom-left, converted to inches with high precision
        standoff_positions_inch = [
            (self._mm_to_inch(x), self._mm_to_inch(y))
            for x, y in self.MICRO_ATX_STANDOFFS
        ]

        # Calculate center position in the overall chassis
        chassis_center_x = self.depth / 2
        chassis_center_y = 0

        # Calculate micro-ATX board bottom-left corner position
        board_bl_x = chassis_center_x - self.micro_atx_depth_inch / 2
        board_bl_y = chassis_center_y - self.micro_atx_width_inch / 2

        # Mini-ITX standoffs to exclude (since they were already added)
        mini_itx_standoffs = set(
            [
                (self._mm_to_inch(x), self._mm_to_inch(y))
                for x, y in self.MINI_ITX_STANDOFFS
            ]
        )

        # Add only the standoffs that aren't part of the mini-ITX layout
        for pos in standoff_positions_inch:
            if pos not in mini_itx_standoffs:
                # Convert from board coordinates to chassis coordinates
                x = (
                    board_bl_x + pos[1]
                )  # Note: x in CadQuery = depth in our coordinate system
                y = (
                    board_bl_y + pos[0]
                )  # Note: y in CadQuery = width in our coordinate system
                floor_obj = self._add_standoff(floor_obj, x, y)

        return floor_obj

    def _add_atx_standoffs(self, floor_obj):
        """Add ATX standoff pattern to the floor object"""
        # The standoff positions in mm from bottom-left, converted to inches with high precision
        standoff_positions_inch = [
            (self._mm_to_inch(x), self._mm_to_inch(y)) for x, y in self.ATX_STANDOFFS
        ]

        # Calculate center position in the overall chassis
        chassis_center_x = self.depth / 2
        chassis_center_y = 0

        # Calculate ATX board bottom-left corner position
        board_bl_x = chassis_center_x - self.atx_depth_inch / 2
        board_bl_y = chassis_center_y - self.atx_width_inch / 2

        # Micro-ATX standoffs to exclude (since they were already added)
        micro_atx_standoffs = set(
            [
                (self._mm_to_inch(x), self._mm_to_inch(y))
                for x, y in self.MICRO_ATX_STANDOFFS
            ]
        )

        # Add only the standoffs that aren't part of the micro-ATX layout
        for pos in standoff_positions_inch:
            if pos not in micro_atx_standoffs:
                # Convert from board coordinates to chassis coordinates
                x = (
                    board_bl_x + pos[1]
                )  # Note: x in CadQuery = depth in our coordinate system
                y = (
                    board_bl_y + pos[0]
                )  # Note: y in CadQuery = width in our coordinate system
                floor_obj = self._add_standoff(floor_obj, x, y)

        return floor_obj

    def _add_e_atx_standoffs(self, floor_obj):
        """Add E-ATX standoff pattern to the floor object"""
        # The standoff positions in mm from bottom-left, converted to inches with high precision
        standoff_positions_inch = [
            (self._mm_to_inch(x), self._mm_to_inch(y)) for x, y in self.E_ATX_STANDOFFS
        ]

        # Calculate center position in the overall chassis
        chassis_center_x = self.depth / 2
        chassis_center_y = 0

        # Calculate E-ATX board bottom-left corner position
        board_bl_x = chassis_center_x - self.e_atx_depth_inch / 2
        board_bl_y = chassis_center_y - self.e_atx_width_inch / 2

        # ATX standoffs to exclude (since they were already added)
        atx_standoffs = set(
            [(self._mm_to_inch(x), self._mm_to_inch(y)) for x, y in self.ATX_STANDOFFS]
        )

        # Add only the standoffs that aren't part of the ATX layout
        for pos in standoff_positions_inch:
            if pos not in atx_standoffs:
                # Convert from board coordinates to chassis coordinates
                x = (
                    board_bl_x + pos[1]
                )  # Note: x in CadQuery = depth in our coordinate system
                y = (
                    board_bl_y + pos[0]
                )  # Note: y in CadQuery = width in our coordinate system
                floor_obj = self._add_standoff(floor_obj, x, y)

        return floor_obj

    def _add_standoff(self, floor_obj, x, y):
        """Add a standoff at the specified position"""
        # Standard 6.35mm (1/4") standoff hole diameter
        standoff_diameter = self._mm_to_inch(
            6.35
        )  # Diameter of standoff hole in inches

        try:
            floor_obj = (
                floor_obj.faces(">Z")  # Select top face
                .workplane()
                .moveTo(x - self.depth / 2, y)  # Position relative to workplane center
                .circle(standoff_diameter / 2)
                .cutThruAll()  # Cut through the floor
            )
        except Exception as e:
            print(f"Error adding standoff at ({x}, {y}): {str(e)}")

        return floor_obj

    def get_main_object(self):
        """Override to return the floor object as the main object"""
        return self.get_component("floor")

    def get_practical_dimensions(self, explosion_distance=None):
        """Get practical dimensions of the floor segment"""
        if explosion_distance is None:
            explosion_distance = self.explosion_distance

        # If exploded, add explosion distance to the height
        return (
            self.segment_depth,
            self.segment_width,
            self.thickness + (explosion_distance if self.exploded else 0),
        )

    def explode(self, distance=None):
        """Explode the floor segment upward only"""
        if distance is None:
            distance = self.explosion_distance

        super().explode(distance)

        # Explode upward for visual clarity
        self.translate((0, 0, distance))

        return self

    def unexplode(self):
        """Return floor segment to its original position"""
        if not self.exploded:
            return self

        distance = self.explosion_distance

        # Return to original position
        self.translate((0, 0, -distance))

        super().unexplode()
        return self

    def translate(self, vector):
        """Translate the floor segment"""
        floor_obj = self.get_component("floor")
        if floor_obj:
            floor_obj = floor_obj.translate(vector)
            self.add_component("floor", floor_obj)

        super().translate(vector)
        return self
