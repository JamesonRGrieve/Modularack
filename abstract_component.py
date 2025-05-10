from abc import ABC, abstractmethod


class AbstractComponent(ABC):
    """An abstract base class for objects that can be exploded for visualization"""

    def __init__(self, explode=False, explosion_distance=5):
        """
        Initialize an explodable object

        Args:
            explode: Whether to explode the object immediately
            explosion_distance: Distance to explode components
        """
        self.exploded = explode
        self.explosion_distance = explosion_distance
        self.components = {}  # Dictionary to store individual CAD objects
        self.child_components = (
            {}
        )  # Dictionary to store child AbstractComponent objects
        self.always_visible_components = (
            set()
        )  # Set of component names that should always be shown
        self.name = self.__class__.__name__.lower()

    @abstractmethod
    def _create_components(self):
        """Create the components of the object (to be implemented by subclasses)"""
        pass

    @abstractmethod
    def get_practical_dimensions(self, explosion_distance=None):
        """
        Calculate practical dimensions including explosion distances

        Args:
            explosion_distance: Optional override for explosion distance

        Returns:
            (practical_x, practical_y, practical_z) tuple
        """
        pass

    def add_component(self, name, component, always_visible=False):
        """
        Add a CAD component to the object

        Args:
            name: Name of the component
            component: Component CAD object
            always_visible: If True, this component will always be shown, even when child components exist

        Returns:
            The added component
        """
        self.components[name] = component
        if always_visible:
            self.always_visible_components.add(name)
        return component

    def add_child_component(self, name, component):
        """
        Add a child component that is itself an AbstractComponent

        Args:
            name: Name for the child component
            component: The AbstractComponent instance

        Returns:
            The added component
        """
        if not isinstance(component, AbstractComponent):
            raise TypeError("Child component must be an AbstractComponent")

        # Store only in child_components - we don't need to duplicate the object
        # in the components dictionary since child components manage their own objects
        self.child_components[name] = component
        return component

    def get_component(self, name):
        """
        Get a component by name

        Args:
            name: Name of the component

        Returns:
            The component object or None if not found
        """
        return self.components.get(name)

    def get_child_component(self, name):
        """
        Get a child component by name

        Args:
            name: Name of the child component

        Returns:
            The AbstractComponent object or None if not found
        """
        return self.child_components.get(name)

    def get_main_object(self):
        """
        Get the main CAD object representing this component.
        Subclasses should override this if they have a specific primary object.

        Returns:
            The main CAD object
        """
        return next(iter(self.components.values())) if self.components else None

    def get_always_visible_components(self):
        """
        Get a dictionary of components that should always be visible, even when child components exist

        Returns:
            Dictionary of {name: component} for components marked as always visible
        """
        return {
            name: self.components[name]
            for name in self.always_visible_components
            if name in self.components
        }

    def explode(self, distance=None):
        """
        Explode the components outward by the specified distance

        Args:
            distance: Distance to explode components, defaults to self.explosion_distance

        Returns:
            Self for method chaining
        """
        if distance is None:
            distance = self.explosion_distance

        self.exploded = True

        # Explode all child components
        for child in self.child_components.values():
            child.explode(distance)

        return self

    def unexplode(self):
        """
        Restore components to their original positions

        Returns:
            Self for method chaining
        """
        if self.exploded:
            # Unexplode all child components
            for child in self.child_components.values():
                child.unexplode()

            self.exploded = False
        return self

    def translate(self, vector):
        """
        Translate all components by the specified vector

        Args:
            vector: (x, y, z) translation vector

        Returns:
            Self for method chaining
        """
        # Translate all child components
        for child in self.child_components.values():
            child.translate(vector)

        return self
