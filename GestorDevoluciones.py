# -*- coding: utf-8 -*-

from multiprocessing import Process, Queue
from string import Template
import socket
import sys
import random
import uuid
import datetime

from rdflib import Namespace, Graph, RDF
from rdflib.namespace import FOAF
from rdflib.term import Literal
from flask import Flask, request

from AgentUtil.ACLMessages import get_message_properties, build_message, send_message
from AgentUtil.FlaskServer import shutdown_server
from AgentUtil.OntoNamespaces import ACL
from AgentUtil.Agent import Agent
import requests

import logging
logging.basicConfig(level=logging.DEBUG)

import Constants.Constants as Constants

# Configuration stuff
hostname = '127.0.1.1'
port = 9022

agn = Namespace(Constants.ONTOLOGY)

# Contador de mensajes
mss_cnt = 0

# Datos del Agente

GestorDevoluciones = Agent('GestorDevoluciones',
                       agn.GestorDevoluciones,
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
    """
    Entrypoint de comunicacion
    """
    req = Graph()
    req.parse(data=request.args['content'])
    message_properties = get_message_properties(req)
    content = message_properties['content']
    accion = str(req.value(subject=content, predicate=RDF.type))
    logging.info('Accion: ' + accion)
    if accion == 'Devolver':
        return devolver(req,content)
    elif accion == 'Buscar_Productos_Usuario':
        return buscar_productos_usuario(req, content)
    

def get_producto(nombre):
    productos = Graph().parse('./data/product.owl')
    sparql_query = Template('''
        SELECT ?producto ?nombre ?precio ?peso ?tieneMarca
        WHERE {
            ?producto rdf:type ?type_prod .
            ?producto pontp:nombre ?nombre .
            ?producto pontp:precio ?precio .
            ?producto pontp:peso ?peso .
            ?producto pontp:tieneMarca ?tieneMarca .
            FILTER (
                ?nombre = '$nombre' 
            )
        }
    ''').substitute(dict(
        nombre = nombre
    ))
    result = productos.query(
        sparql_query,
        initNs=dict(
            rdf=RDF,
            pontp=Namespace("http://www.products.org/ontology/property/")
        )
    )
    producto = next(iter(result))
    logging.info(producto)
    return dict(
        precio=producto.precio,
        peso=producto.peso,
        tieneMarca=producto.tieneMarca
    )


def buscar_productos_usuario(req, content):
    id_usuario = req.value(subject=content, predicate=agn['id_usuario'])
    logging.info(id_usuario)      
    return build_response_devolver(id_usuario)


def build_response_devolver(id_usuario):
    historial_compras = Graph().parse('./data/historial_compras.owl')
    logging.info("ID Usuario en la busqueda " + id_usuario)
    sparql_query = Template('''
        SELECT DISTINCT ?compra ?product ?id ?id_usuario
        WHERE {
            ?compra rdf:type ?type_prod .
            ?compra ns:product ?product .
            ?compra ns:id_usuario ?id_usuario .
            ?compra ns:id ?id .
            FILTER (
                ?id_usuario = '$id_usuario'
            )
        }
    ''').substitute(dict(
        id_usuario = id_usuario
    ))
    result = historial_compras.query(
        sparql_query,
        initNs=dict(
            rdf=RDF,
            ns=agn,
    ))
    i = 0
    result_message = Graph()
    for x in result:
        producto = agn[x.product + '_' + i]
        result_message.add((producto, RDF.type, agn.product))
        result_message.add((producto, agn.nombre, x.product))
        result_message.add((producto, agn.id_compra, x.id))
        i = i + 1
    return result_message.serialize(format='xml')

def devolver(req, content):
    logging.info('Empezamos devolucion')
    id_usuario = req.value(subject=content, predicate=agn.id_usuario)
    logging.info('ID Usuario devolucion = ' + id_usuario)
    motivo = str(req.value(subject=content, predicate=agn.motivo))
    logging.info('Motivo devolucion = ' + motivo)
    nombre = req.value(subject=content, predicate=agn.producto)
    logging.info('Nombre producto de devolucion = ' + str(nombre))
    id_compra = req.value(subject=content, predicate=agn.id_compra)
    logging.info('ID Compra de producto de devolucion = ' + str(id_compra))
    tarjeta = req.value(subject=content, predicate=agn.tarjeta)
    logging.info('Tarjeta del cliente = ' + str(tarjeta))

    resultado = 'null'
    precio = 0

    if motivo == 'equivocado':
        resultado = 'Devolucion por equivocacion aceptada'
        precio = int(get_producto(nombre)['precio'])
    elif motivo == 'defectuoso':
        prob_dev = random.randint(0, 100)
        if prob_dev < 90:
            resultado = 'Devolucion por producto defectuoso aceptada'
            precio = int(get_producto(nombre)['precio'])
        else:
            resultado = 'Devolucion rechazada'
    else:
        prob_dev = random.randint(0, 100)
        if prob_dev < 70:
            resultado = 'Devolucion por producto que no satisface las necesidades del comprador aceptada'
            precio = int(get_producto(nombre)['precio'])
        else:
            resultado = 'Devolucion rechazada'
    logging.info('Resultado: ' + resultado)

    result_message = Graph()
    respuesta = agn['respuesta' + str(mss_cnt)]
    result_message.add((respuesta, RDF.type, agn.respuesta))
    result_message.add((respuesta, agn.resultado, Literal(resultado)))

    if precio > 0:
        id_compra_elim = agn['compra_' + str(id_compra)]
        logging.info(id_compra_elim)
        historial_compras = Graph().parse('./data/historial_compras.owl')
        historial_compras.remove((id_compra_elim, agn.product, Literal(nombre)))
        historial_compras.serialize('./data/historial_compras.owl')

        Pagador = GestorDevoluciones.directory_search(DirectoryAgent, agn.Pagador)
        gCobrar = Graph()
        cobrar = agn['pagar_' + str(mss_cnt)]
        gCobrar.add((cobrar, RDF.type, Literal('Pagar')))
        gCobrar.add((cobrar, agn.tarjeta_bancaria, Literal(tarjeta)))
        gCobrar.add((cobrar, agn.precio_total, Literal(precio)))
        message = build_message(
            gCobrar,
            perf=Literal('request'),
            sender=GestorDevoluciones.uri,
            receiver=Pagador.uri,
            msgcnt=mss_cnt,
            content=cobrar
        )
        Pagado_correctamente = send_message(message, Pagador.address)
        for item in Pagado_correctamente.subjects(RDF.type, Literal('RespuestaPago')):
            for RespuestaCobro in Pagado_correctamente.objects(item, agn.respuesta_cobro):
                logging.info(str(RespuestaCobro))
        logging.info("pago realizado")

    return result_message.serialize(format='xml')

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
    GestorDevoluciones.register_agent(DirectoryAgent)
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


