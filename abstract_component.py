from abc import ABC, abstractmethod


class ExplodableObject(ABC):
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
        self.components = {}  # Dictionary to store components
    
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
    
    def add_component(self, name, component):
        """
        Add a component to the object
        
        Args:
            name: Name of the component
            component: Component object
            
        Returns:
            The added component
        """
        self.components[name] = component
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
        # Implementation to be provided by subclasses through overriding
        return self
    
    def unexplode(self):
        """
        Restore components to their original positions
        
        Returns:
            Self for method chaining
        """
        if self.exploded:
            # Implementation to be provided by subclasses
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
        # Implementation to be provided by subclasses
        return self
    
    def show(self, name_suffix=""):
        """
        Show all components in the viewer
        
        Args:
            name_suffix: Suffix to add to component names for identification
        """
        # Implementation to be provided by subclasses
        pass