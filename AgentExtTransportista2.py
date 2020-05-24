# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
from string import Template
import socket
import random
import uuid

from rdflib import Namespace, Graph, RDF
from rdflib.namespace import FOAF
from rdflib.term import Literal
from flask import Flask, request

from AgentUtil.ACLMessages import get_message_properties, build_message, send_message
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.Agent import Agent
from AgentUtil.OntoNamespaces import ACL
import requests
import logging
logging.basicConfig(level=logging.DEBUG)
import Constants.Constants as Constants


# Configuration stuff
hostname = '127.0.1.1'
port = 9005

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

precio_oferta = 0

# Datos del Agente

AgentExtTransportista2 = Agent('Transportista2',
                       agn.Transportista2,
                       'http://%s:%d/comm' % (hostname, port),
                       'http://%s:%d/Stop' % (hostname, port))

# Directory agent address
DirectoryAgent = Agent('DirectoryAgent',
                       agn.Directory,
                       'http://%s:9000/Register' % hostname,
                       'http://%s:9000/Stop' % hostname)


# Global triplestore graph
dsgraph = Graph()

cola1 = Queue()

# Flask stuff
app = Flask(__name__)


@app.route("/comm")
def comunicacion():
    req = Graph()
    req.parse(data=request.args['content'])
    message_properties = get_message_properties(req)
    content = message_properties['content']
    accion = str(req.value(subject=content, predicate=RDF.type))
    logging.info('Accion: ' + accion)
    if accion == 'Negociar':        
        return negociar(req, content)
    elif accion == 'Transportar':
        return transportar(req, content)

def negociar(req, content):
    global mss_cnt
    global precio_oferta

    mss_cnt = mss_cnt + 1
    precio_oferta = random.randint(200, 500)
    logging.info('Precio oferta: ' + str(precio_oferta))
    graph = Graph()
    oferta = agn['oferta_' + str(mss_cnt)]
    graph.add((oferta, RDF.type, Literal('Oferta_Transportista')))
    graph.add((oferta, agn.oferta, Literal(precio_oferta)))
    return graph.serialize(format='xml')

def transportar(req, content):
    global mss_cnt
    global precio_oferta

    mss_cnt = mss_cnt + 1
    logging.info('Transporte recibido:')
    for item in req.subjects(RDF.type, agn.product):
        nombre = req.value(subject=item, predicate=agn.nombre)
        logging.info(nombre)
    logging.info('Precio envio: ' + str(precio_oferta))

    return Graph().serialize(format='xml')


@app.route("/Stop")
def stop():
    """
    Entrypoint que para el agente

    :return:
    """
    tidyup()
    shutdown_server()
    return "Parando Servidor"


def tidyup():
    """
    Acciones previas a parar el agente

    """
    pass


def agentbehavior1(cola):
    """
    Un comportamiento del agente

    :return:
    """
    AgentExtTransportista2.register_agent(DirectoryAgent)
    pass


if __name__ == '__main__':
    # Ponemos en marcha los behaviors
    ab1 = Process(target=agentbehavior1, args=(cola1,))
    ab1.start()

    # Ponemos en marcha el servidor
    app.run(host=hostname, port=port)

    # Esperamos a que acaben los behaviors
    ab1.join()
    print('The End')


