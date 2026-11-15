import os
import live2d
import pygame
from pygame.locals import DOUBLEBUF, OPENGL

pygame.init()
live2d.init()
pygame.display.set_mode((400, 600), DOUBLEBUF | OPENGL)
live2d.glInit()
model = live2d.Model()
model.LoadModelJson(os.path.join('model', 'GothL2D', 'GothL2D.model3.json'))
model.Resize(400, 600)
model.SetAutoBlink(True)
model.SetAutoBreath(True)
clock = pygame.time.Clock()
running = True
while running:
	for event in pygame.event.get():
		if event.type == pygame.QUIT:
			running = False
	live2d.clearBuffer()
	model.Update()
	model.Draw()
	pygame.display.flip()
	clock.tick(60)
live2d.dispose()
pygame.quit()
