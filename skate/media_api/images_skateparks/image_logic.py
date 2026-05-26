from PIL import Image
from io import BytesIO

def image_resize_800(file):
    """ Resizes image to 800x800 and sets a quality of 85

    Args:
        file (_type_): original image 

    Returns:
        output (BytesIO): image result
    """

    image = Image.open(file)
            
    image.thumbnail((800, 800))
    
    output = BytesIO()
    image.save(output, format=image.format or "JPEG",quality=85)
    output.seek(0)
    return output