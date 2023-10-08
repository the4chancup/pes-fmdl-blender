from struct import pack, unpack
import zlib
import tempfile
import os

def readImageBuffer(stream, imageOffset, chunkCount, uncompressedSize, compressedSize):
	stream.seek(imageOffset, 0)
	
	if chunkCount == 0:
		if compressedSize == 0:
			uncompressedBuffer = bytearray(uncompressedSize)
			if stream.readinto(uncompressedBuffer) != len(uncompressedBuffer):
				return None
			return uncompressedBuffer
		else:
			compressedBuffer = bytearray(compressedSize)
			if stream.readinto(compressedBuffer) != len(compressedBuffer):
				return None
			return zlib.decompress(compressedBuffer)
	
	chunks = []
	for i in range(chunkCount):
		header = bytearray(8)
		if stream.readinto(header) != len(header):
			return None
		(
			compressedSize,
			uncompressedSize,
			offset,
		) = unpack('< HH I', header)
		isCompressed = (offset & (1 << 31)) == 0
		offset &= ~(1 << 31)
		
		chunks.append((offset, compressedSize, isCompressed))
	
	imageBuffers = []
	for (offset, compressedSize, isCompressed) in chunks:
		stream.seek(imageOffset + offset, 0)
		compressedBuffer = bytearray(compressedSize)
		if stream.readinto(compressedBuffer) != len(compressedBuffer):
			return None
		if isCompressed:
			try:
				decompressedBuffer = zlib.decompress(compressedBuffer)
			except:
				return None
		else:
			decompressedBuffer = compressedBuffer
		imageBuffers.append(decompressedBuffer)
	return b''.join(imageBuffers)

def ftexToDds(ftexFilename, ddsFilename):
	inputStream = open(ftexFilename, 'rb')
	
	header = bytearray(64)
	if inputStream.readinto(header) != len(header):
		return False
	
	(
		ftexMagic,
		ftexVersion,
		ftexPixelFormat,
		ftexWidth,
		ftexHeight,
		ftexDepth,
		ftexMipmapCount,
		ftexNrt,
		ftexFlags,
		ftexUnknown1,
		ftexUnknown2,
		ftexTextureType,
		ftexFtexsCount,
		ftexUnknown3,
		ftexHash1,
		ftexHash2,
	) = unpack('< 4s f HHHH  BB HIII  BB 14x  8s 8s', header)
	
	if ftexMagic != b'FTEX':
		return False
	
	if ftexVersion < 2.025:
		return False
	if ftexVersion > 2.045:
		return False
	if ftexFtexsCount > 0:
		return False
	if ftexMipmapCount == 0:
		return False
	
	
	
	ddsFlags = (
		  0x1        # capabilities
		| 0x2        # height
		| 0x4        # width
		| 0x1000     # pixel format
	)
	ddsCapabilities1 = 0x1000 # texture
	ddsCapabilities2 = 0
	
	if (ftexTextureType & 4) != 0:
		# Cube map, with six faces
		if ftexDepth > 1:
			return False
		imageCount = 6
		ddsDepth = 1
		ddsCapabilities1 |= 0x8    # complex
		ddsCapabilities2 |= 0xfe00 # cube map with six faces
		
		ddsExtensionDimension = 3 # 2D
		ddsExtensionFlags = 0x4 # cube map
	elif ftexDepth > 1:
		# Volume texture
		imageCount = 1
		ddsDepth = ftexDepth
		ddsFlags |= 0x800000      # depth
		ddsCapabilities2 |= 0x200000 # volume texture
		
		ddsExtensionDimension = 4 # 3D
		ddsExtensionFlags = 0
	else:
		# Regular 2D texture
		imageCount = 1
		ddsDepth = 1
		
		ddsExtensionDimension = 3 # 2D
		ddsExtensionFlags = 0
	
	if ftexMipmapCount > 1:
		ddsMipmapCount = ftexMipmapCount
		mipmapCount = ftexMipmapCount
		ddsFlags |= 0x20000          # mipmapCount
		ddsCapabilities1 |= 0x8      # complex
		ddsCapabilities1 |= 0x400000 # mipmap
	else:
		ddsMipmapCount = 0
		mipmapCount = 1
	
	
	
	#
	# A frame is a byte array containing a single mipmap element of a single image.
	# Cube maps have six images with mipmaps, and so 6 * $mipmapCount frames.
	# Other textures just have $mipmapCount frames.
	#
	frameSpecifications = []
	for i in range(imageCount):
		for j in range(mipmapCount):
			mipmapHeader = bytearray(16)
			if inputStream.readinto(mipmapHeader) != len(mipmapHeader):
				return None
			(
				offset,
				uncompressedSize,
				compressedSize,
				index,
				ftexsNumber,
				chunkCount,
			) = unpack('< I I I BB H', mipmapHeader)
			if index != j:
				return False
			
			frameSpecifications.append((offset, chunkCount, uncompressedSize, compressedSize))
	
	frames = []
	for (offset, chunkCount, uncompressedSize, compressedSize) in frameSpecifications:
		frame = readImageBuffer(inputStream, offset, chunkCount, uncompressedSize, compressedSize)
		if frame == None:
			return False
		frames.append(frame)
	
	
	
	#
	# Pixel formats:
	#
	#  0 -- DXGI_FORMAT_R8G8B8A8_UNORM
	#  1 -- DXGI_FORMAT_R8_UNORM
	#  2 -- BC1U ["DXT1"]
	#  3 -- BC2U ["DXT3"]
	#  4 -- BC3U ["DXT5"]
	#  8 -- BC4U [DXGI_FORMAT_BC4_UNORM]
	#  9 -- BC5U [DXGI_FORMAT_BC5_UNORM]
	# 10 -- BC6H_UF16 [DXGI_FORMAT_BC6H_UF16]
	# 11 -- BC7U [DXGI_FORMAT_BC7_UNORM]
	# 12 -- DXGI_FORMAT_R16G16B16A16_FLOAT
	# 13 -- DXGI_FORMAT_R32G32B32A32_FLOAT
	# 14 -- DXGI_FORMAT_R10G10B10A2_UNORM
	# 15 -- DXGI_FORMAT_R11G11B10_FLOAT
	#
	# Format support:
	#  PES18: 0-4
	#  PES19: 0-4, 8-15
	#
	
	ddsPitch = None
	if ftexPixelFormat == 0:
		ddsPitchOrLinearSize = 4 * ftexWidth
		ddsFlags |= 0x8 # pitch
		useExtensionHeader = False
		
		ddsFormatFlags = 0x41 # uncompressed rgba
		ddsFourCC = b'\0\0\0\0'
		ddsRgbBitCount = 32
		ddsRBitMask = 0x00ff0000
		ddsGBitMask = 0x0000ff00
		ddsBBitMask = 0x000000ff
		ddsABitMask = 0xff000000
	else:
		ddsPitchOrLinearSize = len(frames[0])
		ddsFlags |= 0x80000 # linear size
		
		ddsFormatFlags = 0x4 # compressed
		ddsRgbBitCount = 0
		ddsRBitMask = 0
		ddsGBitMask = 0
		ddsBBitMask = 0
		ddsABitMask = 0
		
		ddsFourCC = None
		ddsExtensionFormat = None
		
		if ftexPixelFormat == 1:
			ddsExtensionFormat = 61
		elif ftexPixelFormat == 2:
			ddsFourCC = b'DXT1'
		elif ftexPixelFormat == 3:
			ddsFourCC = b'DXT3'
		elif ftexPixelFormat == 4:
			ddsFourCC = b'DXT5'
		elif ftexPixelFormat == 8:
			ddsExtensionFormat = 80
		elif ftexPixelFormat == 9:
			ddsExtensionFormat = 83
		elif ftexPixelFormat == 10:
			ddsExtensionFormat = 95
		elif ftexPixelFormat == 11:
			ddsExtensionFormat = 98
		elif ftexPixelFormat == 12:
			ddsExtensionFormat = 10
		elif ftexPixelFormat == 13:
			ddsExtensionFormat = 2
		elif ftexPixelFormat == 14:
			ddsExtensionFormat = 24
		elif ftexPixelFormat == 15:
			ddsExtensionFormat = 26
		else:
			return False
		
		if ddsExtensionFormat is not None:
			ddsFourCC = b'DX10'
			useExtensionHeader = True
		else:
			useExtensionHeader = False
	
	
	
	outputStream = open(ddsFilename, 'wb')
	
	outputStream.write(pack('< 4s 7I 44x 2I 4s 5I 2I 12x',
		b'DDS ',
		
		124, # header size
		ddsFlags,
		ftexHeight,
		ftexWidth,
		ddsPitchOrLinearSize,
		ddsDepth,
		ddsMipmapCount,
		
		32, # substructure size
		ddsFormatFlags,
		ddsFourCC,
		ddsRgbBitCount,
		ddsRBitMask,
		ddsGBitMask,
		ddsBBitMask,
		ddsABitMask,
		
		ddsCapabilities1,
		ddsCapabilities2,
	))
	
	if useExtensionHeader:
		outputStream.write(pack('< 5I',
			ddsExtensionFormat,
			ddsExtensionDimension,
			ddsExtensionFlags,
			1, # array size
			0, # flags
		))
	
	for frame in frames:
		outputStream.write(frame)
	
	outputStream.close()
	
	return True

def blenderImageLoadFtex(blenderImage, tempDir):
	originalFilename = blenderImage.filepath
	pos = originalFilename.replace("\\", "/").rfind('/')
	if pos == -1:
		baseName = originalFilename
	else:
		baseName = originalFilename[pos + 1:]
	
	try:
		# tempDir is not always accessible
		(ddsFileDescriptor, ddsFile) = tempfile.mkstemp(suffix = '.dds', prefix = baseName + '-', dir = tempDir)
	except:
		return False
	os.close(ddsFileDescriptor)
	if not ftexToDds(originalFilename, ddsFile):
		os.remove(ddsFile)
		return False
	
	blenderImage.filepath = ddsFile
	# Read from the pixels buffer to trigger a load operation
	dummy = blenderImage.pixels[0]
	blenderImage.filepath_raw = originalFilename
	
	os.remove(ddsFile)
	return True
