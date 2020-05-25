# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
from string import Template
import socket
import random
import uuid
import datetime

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
    logging.info('Peticion de oferta')
    prioridad_envio = int(req.value(content, agn.prioridad_envio))
    if (prioridad_envio == 1):
        logging.info('Envio en 1 dia')
    else:
        logging.info('Envio sin prioridad')
    precio_oferta = random.randint(200, 500)*(prioridad_envio+1)
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
    prioridad_envio = int(req.value(content, agn.prioridad_envio))
    fecha_recepcion = None
    if (prioridad_envio == 1):
        logging.info('Envío en 1 día')
        fecha_recepcion = datetime.date.today() + datetime.timedelta(days=1)
    else:
        logging.info('Envío sin prioridad')
        extra_days = random.randint(5, 15)
        fecha_recepcion = datetime.date.today() + datetime.timedelta(days=extra_days)
    for item in req.subjects(RDF.type, agn.compra):
        lote = req.value(subject=item, predicate=agn.lote)
        logging.info('Lote: ' + lote)
        direccion = req.value(subject=item, predicate=agn.direccion)
        logging.info('Dirección: ' + direccion)
        codigo_postal = req.value(subject=item, predicate=agn.codigo_postal)
        logging.info('Codigo postal: ' + codigo_postal)
        total_peso = req.value(subject=item, predicate=agn.total_peso)
        logging.info('Total peso: ' + total_peso)
    logging.info('Precio envio: ' + str(precio_oferta))
    logging.info('Fecha envio: ' + str(fecha_recepcion))
    graph = Graph()
    sujeto = agn['respuesta']
    graph.add((sujeto, agn.precio, Literal(precio_oferta)))
    graph.add((sujeto, agn.fecha_recepcion, Literal(fecha_recepcion)))
    return graph.serialize(format='xml')


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
